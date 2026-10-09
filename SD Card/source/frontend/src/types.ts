export type Theme = "luma-glass" | "hearth" | "neon-grid";
export type Page = "home" | "agenda" | "weather" | "todos" | "ambient" | "countdowns" | "transit";

export interface CalendarEvent {
  profile_id?: string;
  id: string;
  calendar_id: string;
  summary: string;
  start: string;
  end: string;
  all_day: boolean;
  location?: string;
  calendar_name?: string;
  calendar_color?: string;
  event_color?: string;
  event_color_id?: string | null;
  etag?: string | null;
  completed?: boolean;
  due_date?: string;
}

export interface WeatherHour {
  time: string;
  temperature: number;
  precipitation_probability: number | null;
  weather_code: number;
  apparent_temperature?: number | null;
  wind_gust_mph?: number | null;
  precipitation_mm?: number | null;
}

export interface Weather {
  observed_at: string;
  temperature: number;
  apparent_temperature: number;
  high: number;
  low: number;
  weather_code: number;
  summary: string;
  attribution: string;
  hourly: WeatherHour[];
  stale: boolean;
  nudge?: {kind:'precipitation'|'wind'|'heat'|'cold';title:string;detail:string;window:string} | null;
}

export interface Notification {
  id: string;
  app_id: string;
  app_name: string;
  title: string;
  body: string;
  received_at: string;
  category: string;
}

export interface Settings {
  night_clock_enabled?:boolean;
  night_brightness?:number;
  weather_nudges_enabled?: boolean;
  weather_rain_percent?: number;
  weather_gust_mph?: number;
  weather_hot_f?: number;
  weather_cold_f?: number;
  timer_focus_minutes?: number;
  timer_break_minutes?: number;
  onboarding_completed?: boolean;
  device_name: string;
  theme: Theme;
  orientation: string;
  brightness: number;
  volume: number;
  timezone: string;
  weather_location_label: string;
  cycle: { page: Page; seconds: number }[];
}

export interface Snapshot {
  presence_transition?: {id:number;remaining_ms:number;arriving:string[];leaving:string[]} | null;
  users?: {profile_id:string;nickname:string;role:'primary'|'secondary'}[];
  user_panels?: UserPanel[];
  personal_timers?: (import('./timerState').TimerState & {profile_id:string;owner:string;owner_present:boolean})[];
  primary_privacy_redacted?: boolean;
  voice_notice?: {id:number;remaining_ms:number};
  agenda?: {date:string;start:string;end:string;wake:string|null;sleep:string|null;stale:boolean;events:CalendarEvent[]}|null;
  countdowns?: import('./countdownState').CountdownView[];
  transit?: import('./transitState').TransitView[];
  room?: import('./roomState').PurifierView | null;
  display?: import('./displayState').DisplayState|null;
  departure?: import('./departureState').Departure | null;
  todo_controls?: {can_update:boolean;stale?:boolean};
  timer?: import('./timerState').TimerState;
  server_time: string;
  settings: Settings;
  state: {
    privacy: "private" | "full";
    display_power: "on" | "off";
    assistant_phase: "idle" | "listening" | "thinking" | "speaking" | "error";
    active_page: Page;
    cycle_paused_until?: string;
    phone_connected: boolean;
  };
  weather: Weather | null;
  calendar: CalendarEvent[];
  ongoing: CalendarEvent[];
  todos: CalendarEvent[];
  notifications: Notification[];
  privacy_redacted: boolean;
}

export interface UserPanel {
  profile_id:string;
  nickname:string;
  configured:boolean;
  calendar:CalendarEvent[];
  ongoing:CalendarEvent[];
  agenda:NonNullable<Snapshot['agenda']>;
  todos:CalendarEvent[];
  todo_controls:{can_update:boolean;stale:boolean};
  google:{authorized:boolean;last_synced:string|null;error:string|null;reconnect_required:boolean};
  departure?:import('./departureState').Departure|null;
}
