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

from app.matching.continuity import penalty_s
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
    # Continuity (Step 2.4): seconds-equivalent cost per visit by a new carer (recent: half).
    continuity_weight_s: int = 0


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


def _check_penalties(scenario: Scenario, params: SolverParams) -> None:
    """Dropping a visit must always cost more than any travel + continuity it could save,
    otherwise the solver would drop care to protect continuity."""
    max_travel = sum((c.shift_end - c.shift_start) * 60 for c in scenario.carers)
    max_continuity = len(scenario.visits) * params.continuity_weight_s
    if params.drop_penalty <= max_travel + max_continuity:
        raise ValueError(
            f"drop_penalty {params.drop_penalty} must exceed max travel + continuity cost "
            f"({max_travel + max_continuity}); lower the continuity weight"
        )


def solve(
    scenario: Scenario,
    matrix: TravelMatrix,
    params: SolverParams | None = None,
    initial: "Solution | None" = None,
) -> Solution:
    """Solve the day. `initial` warm-starts the search from an existing schedule (visits
    not in this scenario are skipped); the result is never worse than that start."""
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
    if params.continuity_weight_s <= 0:
        routing.SetArcCostEvaluatorOfAllVehicles(travel_idx)
    else:
        _check_penalties(scenario, params)
        # Per-carer arc cost: drive + continuity penalty for *arriving* at a visit. Every
        # served visit has exactly one incoming arc, so each penalty is counted once.
        clients = [scenario.client(v.client_ref) for v in visits]
        for k, c in enumerate(carers):
            pen = [penalty_s(cl, c.carer_ref, params.continuity_weight_s) for cl in clients]
            pen += [0] * (2 * n_c)

            def cost_cb(i: int, j: int, pen: list[int] = pen) -> int:
                ni, nj = manager.IndexToNode(i), manager.IndexToNode(j)
                return drive(ni, nj) + pen[nj]

            routing.SetArcCostEvaluatorOfVehicle(routing.RegisterTransitCallback(cost_cb), k)
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
    if initial is None:
        assignment = routing.SolveWithParameters(search)
    else:
        routing.CloseModelWithParameters(search)
        node_of = {v.visit_id: i for i, v in enumerate(visits)}
        by_carer = {r.carer_ref: r for r in initial.routes}
        routes = [
            [
                manager.NodeToIndex(node_of[st.visit_id])
                for st in by_carer[c.carer_ref].stops
                if st.visit_id in node_of
            ]
            if c.carer_ref in by_carer
            else []
            for c in carers
        ]
        start = routing.ReadAssignmentFromRoutes(routes, True)
        if start is None:
            raise ValueError("initial solution is not feasible for this scenario")
        assignment = routing.SolveFromAssignmentWithParameters(start, search)
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
