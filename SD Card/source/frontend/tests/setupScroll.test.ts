import assert from 'node:assert/strict';
import test from 'node:test';
import {scrollSetupToTop} from '../src/setupScroll.ts';

test('nested setup navigation resets only the owning scroll surface',()=>{
  const scrollSurface={scrollTop:412};
  const child={closest(selector:string){
    assert.equal(selector,'.onboarding-shell, .setup-page');
    return scrollSurface;
  }};
  scrollSetupToTop(child as unknown as Element);
  assert.equal(scrollSurface.scrollTop,0);
});

test('missing setup surface does not scroll another page',()=>{
  scrollSetupToTop(null);
  scrollSetupToTop({closest(){return null;}} as unknown as Element);
});
