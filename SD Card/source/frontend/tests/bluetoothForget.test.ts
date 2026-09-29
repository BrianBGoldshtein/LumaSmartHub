import test from "node:test";
import assert from "node:assert/strict";
import {forgetBluetoothPhone} from "../src/bluetoothForget.ts";

test("preview forget clears only preview state and never calls the local API",async()=>{
  let calls=0;
  const request:typeof fetch=async()=>{calls++;throw Error("must not run")};
  assert.deepEqual(await forgetBluetoothPhone(true,"4321",request),{preview:true,bond_removed:false});
  assert.equal(calls,0);
});

test("real forget sends only the PIN and returns the broker bond result",async()=>{
  let requestBody:unknown;
  const request:typeof fetch=async(url,init)=>{
    assert.equal(url,"/api/v1/bluetooth/forget");
    requestBody=JSON.parse(String(init?.body));
    return new Response(JSON.stringify({forgotten:true,bond_removed:true}),{status:200});
  };
  assert.deepEqual(await forgetBluetoothPhone(false,"1234",request),{preview:false,bond_removed:true});
  assert.deepEqual(requestBody,{pin:"1234"});
});

test("forget reports safe API errors without retrying",async()=>{
  let calls=0;
  const request:typeof fetch=async()=>{calls++;return new Response(JSON.stringify({detail:"Incorrect PIN"}),{status:401});};
  await assert.rejects(forgetBluetoothPhone(false,"0000",request),/Incorrect PIN/);
  assert.equal(calls,1);
});
