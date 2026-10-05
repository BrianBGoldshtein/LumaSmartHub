import type {Snapshot} from './types';

export function voiceNoticeDuration(notice:Snapshot['voice_notice'],expired:number|null):number {
  if(!notice||!Number.isSafeInteger(notice.id)||notice.id<=0||notice.id===expired||
     !Number.isFinite(notice.remaining_ms)||notice.remaining_ms<=0)return 0;
  return Math.min(3000,notice.remaining_ms);
}
