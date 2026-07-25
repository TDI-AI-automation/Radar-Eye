import type { CameraFeed } from "@/components/hud/CameraTile";
import vid1 from "@/assets/vid1.mp4.asset.json";
import vid2 from "@/assets/vid2.mp4.asset.json";

export const CAMERAS: CameraFeed[] = [
  {
    id: "CAM-07",
    location: "North Gate · Sector A",
    fps: 30,
    latency: 28,
    confidence: 0.93,
    aiOn: true,
    health: 98,
    videoSrc: vid1.url,
    detections: [
      { label: "MILITARY", confidence: 0.89, distance: "18 m", level: 1, x: 62, y: 38, w: 14, h: 32 },
      { label: "CIVILIAN", confidence: 0.82, distance: "22 m", level: 1, x: 40, y: 46, w: 8, h: 26 },
    ],
  },
  {
    id: "CAM-12",
    location: "Perimeter Fence · Sector B",
    fps: 30,
    latency: 31,
    confidence: 0.99,
    aiOn: true,
    health: 99,
    videoSrc: vid2.url,
    detections: [
      { label: "CIVILIAN", confidence: 0.65, distance: "26 m", level: 2, x: 30, y: 50, w: 8, h: 30 },
    ],
  },
  {
    id: "CAM-18",
    location: "Motor Pool · Sector C",
    fps: 0,
    latency: 0,
    confidence: 0,
    aiOn: false,
    health: 0,
    blank: true,
    detections: [],
  },
  {
    id: "CAM-23",
    location: "South Watchtower · Sector D",
    fps: 0,
    latency: 0,
    confidence: 0,
    aiOn: false,
    health: 0,
    blank: true,
    detections: [],
  },
];

export type Alert = {
  id: string;
  time: string;
  level: 1 | 2 | 3;
  camera: string;
  sector: string;
  message: string;
  ack?: boolean;
};

export const ALERTS: Alert[] = [
  { id: "A-8821", time: "22:15:31", level: 3, camera: "CAM-12", sector: "Sector B", message: "Rifle detected — armed subject approaching fence", ack: true },
  { id: "A-8820", time: "22:15:20", level: 2, camera: "CAM-18", sector: "Sector C", message: "Melee weapon (machete) detected near motor pool" },
  { id: "A-8819", time: "22:15:10", level: 1, camera: "CAM-23", sector: "Sector D", message: "Crowd density rising — 21 persons at south tower" },
  { id: "A-8818", time: "22:14:52", level: 1, camera: "CAM-07", sector: "Sector A", message: "Person detected at north gate approach" },
  { id: "A-8817", time: "22:14:12", level: 2, camera: "CAM-04", sector: "Sector B", message: "Bamboo pole detected — perimeter breach attempt" },
  { id: "A-8816", time: "22:13:40", level: 1, camera: "CAM-31", sector: "Sector E", message: "Vehicle approach — unmarked, verifying transponder" },
  { id: "A-8815", time: "22:13:02", level: 3, camera: "CAM-09", sector: "Sector A", message: "Firearm signature — resolved as friendly patrol", ack: true },
  { id: "A-8814", time: "22:12:11", level: 1, camera: "CAM-15", sector: "Sector C", message: "Person crossing patrol route beta" },
];

export type Incident = {
  id: string;
  level: 1 | 2 | 3;
  object: string;
  camera: string;
  time: string;
  status: "Investigating" | "Resolved" | "Escalated" | "Pending";
  operator: string;
  location: string;
};

export const INCIDENTS: Incident[] = [
  { id: "INC-000124", level: 3, object: "AK-style rifle", camera: "CAM-12", time: "22:18", status: "Investigating", operator: "LT. Rahman", location: "Sector B — Fence" },
  { id: "INC-000123", level: 2, object: "Machete", camera: "CAM-18", time: "22:11", status: "Escalated", operator: "SGT. Karim", location: "Sector C — Motor Pool" },
  { id: "INC-000122", level: 1, object: "Crowd · 21p", camera: "CAM-23", time: "22:05", status: "Pending", operator: "—", location: "Sector D — Watchtower" },
  { id: "INC-000121", level: 3, object: "Firearm (resolved friendly)", camera: "CAM-09", time: "21:52", status: "Resolved", operator: "LT. Rahman", location: "Sector A — Gate" },
  { id: "INC-000120", level: 2, object: "Bamboo pole", camera: "CAM-04", time: "21:34", status: "Resolved", operator: "CPL. Islam", location: "Sector B — East fence" },
  { id: "INC-000119", level: 1, object: "Vehicle approach", camera: "CAM-31", time: "20:12", status: "Resolved", operator: "SGT. Karim", location: "Sector E — Access road" },
];

export type CamRow = {
  id: string;
  status: "Online" | "Offline" | "Degraded";
  fps: number;
  health: number;
  latency: number;
  ai: boolean;
  recording: boolean;
  storage: string;
  location: string;
};

export const CAM_INVENTORY: CamRow[] = Array.from({ length: 18 }).map((_, i) => {
  const status = i === 5 ? "Offline" : i === 11 ? "Degraded" : "Online";
  return {
    id: `CAM-${String(i + 1).padStart(2, "0")}`,
    status,
    fps: status === "Offline" ? 0 : 30,
    health: status === "Offline" ? 0 : status === "Degraded" ? 62 : 90 + (i % 10),
    latency: status === "Offline" ? 0 : 24 + (i % 20),
    ai: status !== "Offline",
    recording: status !== "Offline",
    storage: `${(2 + (i % 4)).toFixed(1)} TB`,
    location: ["North Gate", "East Fence", "Motor Pool", "South Tower", "Armory", "Mess Hall", "HQ", "Comms", "Perimeter"][i % 9],
  };
});
