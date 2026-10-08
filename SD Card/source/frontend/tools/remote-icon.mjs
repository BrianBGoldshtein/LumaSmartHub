// Deterministic, opaque PNG version of the existing concentric Luma SVG mark.
// Build-only Node code; no raster dependency or phone runtime renderer.
import {deflateSync} from 'node:zlib';
function crc32(bytes){let crc=0xffffffff;for(const byte of bytes){crc^=byte;
  for(let bit=0;bit<8;bit++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}return (crc^0xffffffff)>>>0;}
function chunk(name,data){const type=Buffer.from(name),size=Buffer.alloc(4),crc=Buffer.alloc(4);
  size.writeUInt32BE(data.length);crc.writeUInt32BE(crc32(Buffer.concat([type,data])));return Buffer.concat([size,type,data,crc]);}
export function remoteIcon(size){
  if(![180,192,512].includes(size))throw Error('Unsupported Home Screen icon size.');
  const header=Buffer.alloc(13);header.writeUInt32BE(size,0);header.writeUInt32BE(size,4);header[8]=8;header[9]=2;
  const raw=Buffer.alloc(size*(size*3+1)),bg=[16,24,32],accent=[180,225,215];
  const palette=[bg,bg.map((v,i)=>v+(accent[i]-v)*.14),bg.map((v,i)=>v+(accent[i]-v)*.484),accent];
  for(let y=0;y<size;y++)for(let x=0;x<size;x++){
    const color=[0,0,0];
    for(const dy of [.25,.75])for(const dx of [.25,.75]){
      const distance=Math.hypot((x+dx)/size-.5,(y+dy)/size-.5);
      const tone=palette[distance<=20/192?3:distance<=32/192?2:distance<=48/192?1:0];
      for(let i=0;i<3;i++)color[i]+=tone[i]/4;
    }
    const offset=y*(size*3+1)+1+x*3;
    for(let i=0;i<3;i++)raw[offset+i]=Math.round(color[i]);
  }
  return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',header),chunk('IDAT',deflateSync(raw)),chunk('IEND',Buffer.alloc(0))]);
}
