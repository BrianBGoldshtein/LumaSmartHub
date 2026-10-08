// Navigate to a new HTML URL rather than reloading a potentially cached entry
// point. Keep the user's setup route/theme; never delete browser or hub state.
export function dashboardRefreshUrl(currentUrl:string,release?:string,stamp=Date.now()):string {
  const url=new URL(currentUrl);
  url.searchParams.set('ui_refresh',String(stamp));
  if(release)url.searchParams.set('ui_release',release);
  return url.href;
}
