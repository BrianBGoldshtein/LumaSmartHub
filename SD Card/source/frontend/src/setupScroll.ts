/** Keep nested setup steps anchored at their own top, including onboarding. */
export function scrollSetupToTop(node:Element|null){
  const scroller=node?.closest('.onboarding-shell, .setup-page');
  if(scroller)scroller.scrollTop=0;
}
