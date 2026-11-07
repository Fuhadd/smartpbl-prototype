/**
 * Route map (Schedule.dc.html): OpenStreetMap tiles, one coloured route per pinned carer,
 * numbered visit markers in visiting order, square start markers and dashed unassigned
 * visits. Lines join stops in order; they show the sequence, not the roads driven.
 */
import 'leaflet/dist/leaflet.css'

import { divIcon, latLngBounds, type LatLngTuple } from 'leaflet'
import { useEffect, useMemo } from 'react'
import { MapContainer, Marker, Polyline, TileLayer, useMap } from 'react-leaflet'

import type { Run, RunMap } from './api'
import { colourOf, type Pins, textColourOf } from './model'

const OSM_TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)

function visitIcon(n: number, colour: string, text: string, selected: boolean) {
  const style = selected
    ? `background:${colour};color:#fff;border:0;box-shadow:0 0 0 6px ${colour}2e`
    : `background:#fff;color:${text};border:3px solid ${colour}`
  return divIcon({
    className: 'smartpbl-marker',
    html: `<span style="${style};width:26px;height:26px;border-radius:999px;display:flex;align-items:center;justify-content:center;font:700 12px Inter,sans-serif;box-sizing:border-box">${n}</span>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  })
}

function startIcon(colour: string) {
  return divIcon({
    className: 'smartpbl-marker',
    html: `<span style="display:block;width:20px;height:20px;border-radius:5px;background:${colour}"></span>`,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  })
}

const unassignedIcon = divIcon({
  className: 'smartpbl-marker',
  html: '<span style="width:26px;height:26px;border-radius:999px;background:#fff;border:2px dashed #71717A;color:#52525B;display:flex;align-items:center;justify-content:center;font:700 12px Inter,sans-serif;box-sizing:border-box">!</span>',
  iconSize: [26, 26],
  iconAnchor: [13, 13],
})

/** Fit the view to the drawn points whenever the pinned carers change. */
function FitBounds({ points }: { points: LatLngTuple[] }) {
  const map = useMap()
  // A string key, so the effect re-runs when the points change, not on every render.
  const key = points.map((p) => p.join(',')).join(';')
  useEffect(() => {
    const pts = key ? key.split(';').map((p) => p.split(',').map(Number) as LatLngTuple) : []
    if (pts.length) map.fitBounds(latLngBounds(pts), { padding: [32, 32], maxZoom: 14 })
  }, [map, key])
  return null
}

export function RouteMap({
  run,
  places,
  pins,
  selectedVisit,
  onSelectVisit,
}: {
  run: Run
  places: RunMap
  pins: Pins
  selectedVisit: string | null
  onSelectVisit: (visitId: string) => void
}) {
  const visitAt = useMemo(() => new Map(places.visits.map((v) => [v.visit_id, v])), [places])
  const carerAt = useMemo(() => new Map(places.carers.map((c) => [c.carer_ref, c])), [places])

  const routes = run.routes
    .filter((r) => pins.slots.includes(r.carer_ref))
    .map((r) => {
      const start = carerAt.get(r.carer_ref)!.start
      const stops = r.visits.map((a) => ({ a, at: visitAt.get(a.visit_id)!.location }))
      const line: LatLngTuple[] = [[start.lat, start.lon], ...stops.map((s): LatLngTuple => [s.at.lat, s.at.lon])]
      return { ref: r.carer_ref, colour: colourOf(pins, r.carer_ref)!, text: textColourOf(pins, r.carer_ref), stops, line }
    })
  const unassigned = run.dropped
    .map((d) => visitAt.get(String(d.visit_id)))
    .filter((v) => v !== undefined)
  const points = [...routes.flatMap((r) => r.line), ...unassigned.map((v): LatLngTuple => [v.location.lat, v.location.lon])]

  return (
    <div className="relative">
      <MapContainer
        center={[52.48, -1.89]}
        zoom={12}
        scrollWheelZoom={false}
        className="h-[440px] w-full rounded-2xl"
        aria-label="Map of the routes for the pinned carers, with numbered visits and unassigned visits"
      >
        <TileLayer url={OSM_TILES} attribution={OSM_ATTRIBUTION} />
        <FitBounds points={points} />
        {routes.map((r) => (
          <Polyline key={r.ref} positions={r.line} pathOptions={{ color: r.colour, weight: 4, lineJoin: 'round' }} />
        ))}
        {routes.map((r) => (
          <Marker key={`${r.ref}-start`} position={r.line[0]!} icon={startIcon(r.colour)} title={`${r.ref} start`} />
        ))}
        {routes.flatMap((r) =>
          r.stops.map(({ a, at }) => (
            <Marker
              key={a.visit_id}
              position={[at.lat, at.lon]}
              icon={visitIcon(a.sequence, r.colour, r.text, a.visit_id === selectedVisit)}
              title={esc(`${r.ref} visit ${a.sequence}: ${a.client_ref}`)}
              eventHandlers={{ click: () => onSelectVisit(a.visit_id) }}
              keyboard
            />
          )),
        )}
        {unassigned.map((v) => (
          <Marker key={v.visit_id} position={[v.location.lat, v.location.lon]} icon={unassignedIcon} title={`Unassigned: ${v.client_ref}`} />
        ))}
      </MapContainer>
      <div className="absolute bottom-3.5 left-3.5 z-[400] flex flex-wrap gap-3.5 rounded-xl bg-surface px-3 py-2 text-xs text-soft">
        <span className="flex items-center gap-1.5">
          <span className="size-3 rounded-[3px] bg-soft" aria-hidden="true" />
          Carer start
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-3 rounded-full border-2 border-soft" aria-hidden="true" />
          Visit (order)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-3 rounded-full border-2 border-dashed border-[#71717A]" aria-hidden="true" />
          Unassigned
        </span>
      </div>
    </div>
  )
}
