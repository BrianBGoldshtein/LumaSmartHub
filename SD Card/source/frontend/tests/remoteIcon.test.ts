import test from 'node:test';
import assert from 'node:assert/strict';
import {inflateSync} from 'node:zlib';
import {remoteIcon} from '../tools/remote-icon.mjs';
test('Home Screen PNGs are deterministic, opaque and match the Luma mark',()=>{
  for(const size of [180,192,512]){
    const png=remoteIcon(size);assert.deepEqual(png,remoteIcon(size));
    assert.deepEqual([...png.subarray(0,8)],[137,80,78,71,13,10,26,10]);
    assert.equal(png.readUInt32BE(16),size);assert.equal(png.readUInt32BE(20),size);
    assert.equal(png[25],2); // RGB, no transparent pixels or private screenshot.
    const data=inflateSync(png.subarray(41,41+png.readUInt32BE(33)));
    assert.equal(data.length,size*(size*3+1));assert.deepEqual([...data.subarray(1,4)],[16,24,32]);
    const offset=(size/2)*(size*3+1)+1+(size/2)*3;
    assert.deepEqual([...data.subarray(offset,offset+3)],[180,225,215]);
  }
  assert.throws(()=>remoteIcon(1));
});
