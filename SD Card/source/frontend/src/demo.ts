import type { Snapshot } from "./types";

const now = new Date();
const inMinutes = (minutes: number) => new Date(now.getTime() + minutes * 60000).toISOString();

export const demoSnapshot: Snapshot = {
  server_time: now.toISOString(),
  settings: {
    device_name: "Luma",
    theme: "luma-glass",
    orientation: "landscape",
    brightness: 70,
    volume: 55,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    weather_location_label: "Home",
    cycle: [
      { page: "home", seconds: 45 },
      { page: "agenda", seconds: 30 },
      { page: "weather", seconds: 25 },
      { page: "todos", seconds: 25 },
      { page: "ambient", seconds: 14 },
    ],
  },
  state: {
    privacy: "full",
    display_power: "on",
    assistant_phase: "idle",
    active_page: "home",
    phone_connected: true,
  },
  weather: {
    observed_at: now.toISOString(),
    temperature: 68,
    apparent_temperature: 67,
    high: 74,
    low: 57,
    weather_code: 1,
    summary: "Clear skies giving way to soft clouds this evening.",
    attribution: "Weather data by Open-Meteo.com",
    stale: false,
    hourly: [0, 1, 2, 3, 4, 5].map((hour) => ({
      time: inMinutes(hour * 60),
      temperature: 68 - hour,
      precipitation_probability: hour < 4 ? 3 : 12,
      weather_code: hour < 3 ? 1 : 2,
    })),
  },
  calendar: [
    { id: "1", calendar_id: "work", calendar_name: "Work", calendar_color: "#7986cb", summary: "Design review", start: inMinutes(34), end: inMinutes(94), all_day: false, location: "Studio" },
    { id: "2", calendar_id: "personal", calendar_name: "Personal", calendar_color: "#33b679", event_color: "#f6bf26", summary: "Dinner with Maya", start: inMinutes(185), end: inMinutes(275), all_day: false, location: "Little Pine" },
    { id: "3", calendar_id: "personal", calendar_name: "Personal", calendar_color: "#33b679", summary: "Evening reset", start: inMinutes(330), end: inMinutes(350), all_day: false },
  ],
  ongoing: [],
  todos: [
    { id: "t1", calendar_id: "todos", summary: "Replace air filter", start: now.toISOString(), end: inMinutes(1440), all_day: true, due_date:new Intl.DateTimeFormat('en-CA').format(now),calendar_color:'#7986cb',completed:false },
    { id: "t2", calendar_id: "todos", summary: "Send project notes", start: now.toISOString(), end: inMinutes(2880), all_day: true, due_date:inMinutes(1440).slice(0,10),calendar_color:'#7986cb',completed:false },
    { id: "t3", calendar_id: "todos", summary: "Book library room", start: now.toISOString(), end: inMinutes(1440), all_day: true, due_date:new Intl.DateTimeFormat('en-CA').format(now),calendar_color:'#7986cb',event_color:'#7ae7bf',completed:true },
  ],
  notifications: [],
  privacy_redacted: false,
};
