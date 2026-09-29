import test from "node:test";
import assert from "node:assert/strict";
import {networkNotice,networkDescription,type NetworkStatus} from "../src/networkStatus.ts";
const status=(state:NetworkStatus["state"],stale=false):NetworkStatus=>({state,stale,checking_enabled:true,checked_at:null});
test("network notices distinguish portal, offline and limited access",()=>{
  assert.equal(networkNotice(status("portal")),"Network sign-in");
  assert.equal(networkNotice(status("offline")),"Offline · Saved view");
  assert.equal(networkNotice(status("limited")),"Limited internet");
});
test("healthy, unavailable and stale checks never falsely demand sign-in",()=>{
  for(const state of ["online","unknown","unavailable"] as const)assert.equal(networkNotice(status(state)),null);
  assert.equal(networkNotice(status("portal",true)),null);
  assert.equal(networkNotice(),null);
  assert.match(networkDescription(status("unknown")),/not been verified/);
  assert.match(networkDescription(status("unavailable")),/unavailable/);
});
