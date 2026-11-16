export const settingsGroups = [
  { id: 'display', title: 'Display & weather', detail: 'Theme, brightness, location & night mode', panels: [
    { id: 'appearance', title: 'Theme & brightness', detail: 'Daytime brightness and the look of Luma' },
    { id: 'location', title: 'Location & orientation', detail: 'Weather location, timezone and screen rotation' },
    { id: 'night', title: 'Night & wake', detail: 'Night clock, dimming and the wake transition' },
    { id: 'weather-hints', title: 'Weather hints', detail: 'Rain, wind and temperature reminders' },
  ] },
  { id: 'networking', title: 'Network & remote', detail: 'Wi-Fi, hotspot, Tailscale & iPhone remote', panels: [
    { id: 'wifi', title: 'Wi-Fi', detail: 'Find networks, check internet and open a sign-in page' },
    { id: 'hotspot', title: 'Room-device hotspot', detail: 'Share Luma’s internet with room devices' },
    { id: 'iphone-remote', title: 'iPhone remote & Tailscale', detail: 'Private connection, enrollment and access' },
    { id: 'shortcuts', title: 'Siri Shortcuts', detail: 'View or replace the private command token' },
  ] },
  { id: 'people', title: 'People & privacy', detail: 'Users, Bluetooth phones & PIN', panels: [
    { id: 'user-accounts', title: 'Users', detail: 'Add secondary users and manage their setup' },
    { id: 'bluetooth', title: 'Bluetooth phones', detail: 'Pair a phone or manage an existing connection' },
    { id: 'privacy-pin', title: 'Privacy PIN', detail: 'Change the PIN or temporarily show private content' },
  ] },
  { id: 'calendar', title: 'Calendar & routines', detail: 'Google Calendar, to-dos, reminders & timers', panels: [
    { id: 'google-calendar', title: 'Google Calendar', detail: 'Google sign-in, agenda, to-dos and Sleep calendar' },
    { id: 'departure', title: 'Leave soon', detail: 'Calendars and timing for departure reminders' },
    { id: 'countdowns', title: 'Important dates', detail: 'Count down to saved dates and linked events' },
    { id: 'focus', title: 'Focus & break', detail: 'Default focus and break timer lengths' },
    { id: 'transit', title: 'Transit', detail: 'Saved stops and departures' },
  ] },
  { id: 'audio', title: 'Sound & voice', detail: 'Hey Luma, speakers & chimes', panels: [
    { id: 'voice', title: 'Hey Luma', detail: 'Microphone, calibration and spoken replies' },
    { id: 'speaker', title: 'Speaker output', detail: 'Choose the device for Luma’s audio' },
    { id: 'chimes', title: 'Notification sounds', detail: 'Preview and choose alert chimes' },
  ] },
  { id: 'room', title: 'Room devices', detail: 'Air purifier & room scenes', panels: [
    { id: 'purifier', title: 'Air purifier', detail: 'Connect and configure a compatible Levoit purifier' },
    { id: 'scenes', title: 'Room scenes', detail: 'Actions for Morning, Night, Arrive and Away' },
  ] },
  { id: 'system', title: 'System & updates', detail: 'Software, cooling, backups & Pi Connect', panels: [
    { id: 'updates', title: 'Software updates', detail: 'Check the installed version and install updates' },
    { id: 'cooling', title: 'Temperature & cooling', detail: 'CPU temperature and fan controls' },
    { id: 'backup', title: 'Settings backup', detail: 'Save or restore a portable USB backup' },
    { id: 'pi-connect', title: 'Raspberry Pi Connect', detail: 'Set up remote troubleshooting' },
    { id: 'diagnostics', title: 'Device check', detail: 'Run diagnostics on Luma' },
  ] },
] as const;

type SettingsGroup = (typeof settingsGroups)[number];
type SettingsPanel = SettingsGroup['panels'][number];
export type SettingsSection = SettingsGroup['id'] | SettingsPanel['id'];
export type SettingsPanelId = SettingsPanel['id'];

export function settingsDestination(section: string | null | undefined) {
  for (const group of settingsGroups) {
    if (group.id === section) return { group, panel: null };
    const panel = group.panels.find(item => item.id === section);
    if (panel) return { group, panel };
  }
  return null;
}

export function wallSettingsSection(params: URLSearchParams, hash: string) {
  const section = params.get('section');
  if (section === 'connect') return 'updates'; // Older update links.
  return section ?? (hash === '#network' ? 'wifi' : null);
}
