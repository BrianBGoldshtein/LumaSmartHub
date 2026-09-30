export type BluetoothForgetResult={preview:boolean;bond_removed:boolean};

export async function forgetBluetoothPhone(
  demo:boolean,
  pin:string,
  request:typeof fetch=fetch,
):Promise<BluetoothForgetResult>{
  if(demo)return {preview:true,bond_removed:false};

  const response=await request("/api/v1/bluetooth/forget",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({pin}),
  });
  const data=await response.json().catch(()=>({})) as {detail?:unknown;bond_removed?:unknown};
  if(!response.ok)throw Error(typeof data.detail==="string"?data.detail:"Luma could not remove the phone pairing.");
  return {preview:false,bond_removed:data.bond_removed===true};
}
