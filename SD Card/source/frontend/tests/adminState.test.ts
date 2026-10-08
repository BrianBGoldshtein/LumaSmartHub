import test from 'node:test';
import assert from 'node:assert/strict';
import {adminAccess,isAdminNeeded} from '../src/adminState.ts';
import {primaryRemote} from '../src/remote/state.ts';

test('only a bounded explicit server lease or initial bootstrap opens settings',()=>{
  assert.equal(adminAccess({configured:true,unlocked:true,expires_in_seconds:300}),'unlock');
  assert.equal(adminAccess({configured:false,bootstrap:true}),'bootstrap');
  for(const value of [null,{}, {unlocked:true}, {configured:true,bootstrap:true},
      {configured:true,unlocked:true,expires_in_seconds:0}, {configured:true,unlocked:true,expires_in_seconds:301},
      {configured:true,unlocked:true,expires_in_seconds:NaN}])assert.equal(adminAccess(value),'locked');
});

test('admin error requires the fixed code and a boolean freshness field',()=>{
  assert.ok(isAdminNeeded({code:'admin_required',fresh:true}));
  for(const value of [null,{detail:'admin_required'},{code:'admin_required'},{code:'admin_required',fresh:'true'}])assert.ok(!isAdminNeeded(value));
});

test('both primary profile identity and primary role required for admin navigation',()=>{
  assert.ok(primaryRemote({profile_id:'primary',role:'primary'}));
  for(const value of [null,{}, {role:'primary'},{profile_id:'primary',role:'secondary'},
      {profile_id:'guest',role:'primary'}])assert.ok(!primaryRemote(value));
});
