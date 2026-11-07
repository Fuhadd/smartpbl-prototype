"""Baseline carer scheduling as a VRP with time windows (OR-Tools routing library).

Model (Step 2.3):
  - one vehicle per carer; it starts at the carer's start location (home or office);
  - routes are open: each vehicle ends at a dummy node with zero travel, so the trip home
    isn't counted (commuting home is usually unpaid; see ADR-016);
  - one node per visit, at the client's location;
  - "Time" dimension in seconds: transit(i -> j) = service duration at i + drive time i -> j;
    the cumulative value at a visit is when service starts, constrained to its arrival
    window; slack lets a carer wait for a window to open;
  - vehicle start/end cumul constrained to the carer's shift;
  - skills and shift fit: each visit may only be served by eligible carers;
  - each visit is optional with a large drop penalty (time-critical visits doubled), so an
    overloaded day still returns the best partial schedule instead of "infeasible";
  - objective: total drive seconds + drop penalties. Waiting time is not costed yet.
"""

import time
from dataclasses import dataclass, field

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from app.matching.data import Location, Scenario, can_serve
from app.matching.travel import TravelMatrix

DROP_PENALTY = 1_000_000  # seconds-equivalent (~11.6 days of driving): dominates travel
TIME_CRITICAL_FACTOR = 2
MAX_WAIT_S = 4 * 3600
HORIZON_S = 24 * 3600

_STATUS = {
    value: name.removeprefix("ROUTING_")
    for name, value in routing_enums_pb2.RoutingSearchStatus.Value.items()
}
FirstSolution = routing_enums_pb2.FirstSolutionStrategy
Metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic


@dataclass(frozen=True)
class SolverParams:
    time_limit_s: float = 10.0
    first_solution: str = "PARALLEL_CHEAPEST_INSERTION"  # see note 12: PCA drops 47
    metaheuristic: str = "TABU_SEARCH"  # best on the seed-42 instance at 10 s and 60 s
    first_solution_only: bool = False  # stop at the construction heuristic (no local search)
    drop_penalty: int = DROP_PENALTY


@dataclass(frozen=True)
class Stop:
    visit_id: str
    client_ref: str
    start_s: int  # service start (within the arrival window)
    end_s: int  # start + duration
    travel_s: int  # drive time from the previous stop (or the carer's start)


@dataclass(frozen=True)
class Route:
    carer_ref: str
    departs_s: int  # when the carer leaves their start location
    stops: tuple[Stop, ...]

    @property
    def travel_s(self) -> int:
        return sum(s.travel_s for s in self.stops)

    @property
    def service_s(self) -> int:
        return sum(s.end_s - s.start_s for s in self.stops)


@dataclass(frozen=True)
class Solution:
    routes: tuple[Route, ...]
    dropped: tuple[str, ...]
    objective: int
    status: str
    wall_s: float
    params: SolverParams
    matrix_backend: str
    stats: dict[str, float] = field(default_factory=dict)

    @property
    def travel_s(self) -> int:
        return sum(r.travel_s for r in self.routes)

    @property
    def served(self) -> int:
        return sum(len(r.stops) for r in self.routes)


def solve(scenario: Scenario, matrix: TravelMatrix, params: SolverParams | None = None) -> Solution:
    params = params or SolverParams()
    carers, visits = scenario.carers, scenario.visits
    loc_index = matrix.index()
    n_v, n_c = len(visits), len(carers)

    # Nodes: [visits..., carer starts..., dummy ends...]
    node_loc: list[Location | None] = [scenario.client(v.client_ref).location for v in visits]
    node_loc += [c.start for c in carers] + [None] * n_c
    service = [v.duration * 60 for v in visits] + [0] * (2 * n_c)
    starts = list(range(n_v, n_v + n_c))
    ends = list(range(n_v + n_c, n_v + 2 * n_c))

    manager = pywrapcp.RoutingIndexManager(len(node_loc), n_c, starts, ends)
    routing = pywrapcp.RoutingModel(manager)

    def drive(i: int, j: int) -> int:
        a, b = node_loc[i], node_loc[j]
        if a is None or b is None:  # to/from the dummy end: open route
            return 0
        return matrix.durations_s[loc_index[a]][loc_index[b]]

    def travel_cb(from_index: int, to_index: int) -> int:
        return drive(manager.IndexToNode(from_index), manager.IndexToNode(to_index))

    def time_cb(from_index: int, to_index: int) -> int:
        i, j = manager.IndexToNode(from_index), manager.IndexToNode(to_index)
        return service[i] + drive(i, j)

    travel_idx = routing.RegisterTransitCallback(travel_cb)
    time_idx = routing.RegisterTransitCallback(time_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(travel_idx)
    routing.AddDimension(time_idx, MAX_WAIT_S, HORIZON_S, False, "Time")
    time_dim = routing.GetDimensionOrDie("Time")

    for node, v in enumerate(visits):
        index = manager.NodeToIndex(node)
        time_dim.CumulVar(index).SetRange(v.window_start * 60, v.window_end * 60)
        allowed = [k for k, c in enumerate(carers) if can_serve(c, v)]
        # Vehicle variable domain: eligible carers, or -1 (= dropped via the disjunction).
        routing.VehicleVar(index).SetValues([-1, *allowed])
        penalty = params.drop_penalty * (TIME_CRITICAL_FACTOR if v.time_critical else 1)
        routing.AddDisjunction([index], penalty)

    for k, c in enumerate(carers):
        time_dim.CumulVar(routing.Start(k)).SetRange(c.shift_start * 60, c.shift_end * 60)
        time_dim.CumulVar(routing.End(k)).SetRange(c.shift_start * 60, c.shift_end * 60)
        # Prefer late departures/early finishes among equal-cost schedules (tidy timings).
        routing.AddVariableMaximizedByFinalizer(time_dim.CumulVar(routing.Start(k)))
        routing.AddVariableMinimizedByFinalizer(time_dim.CumulVar(routing.End(k)))

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = getattr(FirstSolution, params.first_solution)
    search.local_search_metaheuristic = getattr(Metaheuristic, params.metaheuristic)
    search.time_limit.FromMilliseconds(int(params.time_limit_s * 1000))
    if params.first_solution_only:
        search.solution_limit = 1

    t0 = time.perf_counter()
    assignment = routing.SolveWithParameters(search)
    wall = time.perf_counter() - t0
    status_name = _STATUS.get(routing.status(), str(routing.status()))
    if assignment is None:
        return Solution((), tuple(v.visit_id for v in visits), -1, status_name, wall, params,
                        matrix.backend)  # fmt: skip

    routes: list[Route] = []
    served: set[str] = set()
    for k, c in enumerate(carers):
        index = routing.Start(k)
        departs = assignment.Value(time_dim.CumulVar(index))
        prev = manager.IndexToNode(index)
        stops: list[Stop] = []
        index = assignment.Value(routing.NextVar(index))
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            v = visits[node]
            start = assignment.Value(time_dim.CumulVar(index))
            stops.append(Stop(v.visit_id, v.client_ref, start, start + v.duration * 60,
                              drive(prev, node)))  # fmt: skip
            served.add(v.visit_id)
            prev = node
            index = assignment.Value(routing.NextVar(index))
        routes.append(Route(c.carer_ref, departs, tuple(stops)))

    dropped = tuple(v.visit_id for v in visits if v.visit_id not in served)
    return Solution(
        routes=tuple(routes),
        dropped=dropped,
        objective=assignment.ObjectiveValue(),
        status=status_name,
        wall_s=wall,
        params=params,
        matrix_backend=matrix.backend,
    )
