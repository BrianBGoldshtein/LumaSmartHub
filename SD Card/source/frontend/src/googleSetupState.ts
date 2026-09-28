export function googleCallbackMessage(flag:unknown):string {
  return flag==="1" ? "Sign-in didn’t finish. Try again. Your saved connection has not changed." : "";
}
