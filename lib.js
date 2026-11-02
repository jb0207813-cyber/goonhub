export function detectPlatform(raw) {
  try {
    const url=new URL(raw.trim());
    if(!['http:','https:'].includes(url.protocol)||url.username||url.password)return null;
    const h=url.hostname.toLowerCase().replace(/^www\./,'');
    if(['x.com','twitter.com','mobile.twitter.com','mobile.x.com'].includes(h) && /^\/[\w]{1,15}\/status\/\d+/.test(url.pathname))return 'x';
    if(['instagram.com','m.instagram.com'].includes(h) && /^\/(p|reel|tv)\/[^/]+/.test(url.pathname))return 'instagram';
    if(['facebook.com','m.facebook.com','web.facebook.com','fb.watch'].includes(h))return 'facebook';
    return null;
  }catch{return null}
}
export function safeBackend(input){
  try{const u=new URL(input.trim());if(u.username||u.password||u.search||u.hash||u.pathname!=='/'&&u.pathname!=='')return null;
    if(u.protocol!=='https:'&&!(u.protocol==='http:'&&['localhost','127.0.0.1'].includes(u.hostname)))return null;
    return u.origin;
  }catch{return null}
}
export const readableBytes=(n)=>typeof n==='number'&&n>0?(n>=1073741824?(n/1073741824).toFixed(1)+' GB':n>=1048576?(n/1048576).toFixed(1)+' MB':(n/1024).toFixed(0)+' KB'):'—';
export const platformName=p=>({x:'X',instagram:'Instagram',facebook:'Facebook'})[p]||'Post';
export function safePreview(url){try{const u=new URL(url);return u.protocol==='https:'?u.href:null}catch{return null}}
export const statusName=s=>({queued:'Queued',working:'Downloading',processing:'Processing media',ready:'File ready',error:'Failed',cancelled:'Cancelled'})[s]||s;