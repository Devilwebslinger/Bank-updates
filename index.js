import { buildPushPayload } from "@block65/webcrypto-web-push";

const cors={"Access-Control-Allow-Origin":"*","Access-Control-Allow-Headers":"Content-Type, Authorization","Access-Control-Allow-Methods":"GET, POST, OPTIONS"};
const json=(data,status=200,extra={})=>new Response(JSON.stringify(data),{status,headers:{"Content-Type":"application/json",...cors,...extra}});
const hex=buf=>Array.from(new Uint8Array(buf)).map(b=>b.toString(16).padStart(2,"0")).join("");
async function idFor(endpoint){return hex(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(endpoint)));}
function allowed(req,env){const h=req.headers.get("Authorization")||"";return h===`Bearer ${env.TRIGGER_TOKEN}`;}

export default {
 async fetch(req,env){
  if(req.method==="OPTIONS") return new Response(null,{status:204,headers:cors});
  const url=new URL(req.url);
  try{
   if(url.pathname==="/health"&&req.method==="GET") return json({ok:true,service:"bank-insurance-exam-push"});
   if(url.pathname==="/config"&&req.method==="GET") return json({publicKey:env.VAPID_SERVER_PUBLIC_KEY});
   if(url.pathname==="/subscribe"&&req.method==="POST"){
    const body=await req.json(); const sub=body.subscription||body;
    if(!sub?.endpoint || !sub?.keys?.p256dh || !sub?.keys?.auth) return json({error:"Invalid subscription"},400);
    if(!String(sub.endpoint).startsWith("https://")) return json({error:"HTTPS endpoint required"},400);
    const id=await idFor(sub.endpoint); const now=new Date().toISOString();
    await env.DB.prepare(`INSERT INTO subscriptions (id,endpoint,subscription_json,created_at,updated_at) VALUES (?,?,?,?,?) ON CONFLICT(endpoint) DO UPDATE SET subscription_json=excluded.subscription_json,updated_at=excluded.updated_at`)
      .bind(id,sub.endpoint,JSON.stringify(sub),now,now).run();
    return json({ok:true});
   }
   if(url.pathname==="/unsubscribe"&&req.method==="POST"){
    const body=await req.json(); if(!body.endpoint) return json({error:"endpoint required"},400);
    await env.DB.prepare("DELETE FROM subscriptions WHERE endpoint=?").bind(body.endpoint).run();
    return json({ok:true});
   }
   if(url.pathname==="/notify"&&req.method==="POST"){
    if(!allowed(req,env)) return json({error:"Unauthorized"},401);
    const body=await req.json(); const payload=body.payload||body;
    const rows=await env.DB.prepare("SELECT id,endpoint,subscription_json FROM subscriptions").all();
    let sent=0,removed=0,failed=0;
    for(const row of rows.results||[]){
      try{
       const sub=JSON.parse(row.subscription_json);
       const reqInit=await buildPushPayload({data:JSON.stringify(payload),options:{ttl:86400,urgency:"high"}},sub,{subject:env.VAPID_SUBJECT,publicKey:env.VAPID_SERVER_PUBLIC_KEY,privateKey:env.VAPID_SERVER_PRIVATE_KEY});
       const r=await fetch(sub.endpoint,reqInit);
       if(r.status===404||r.status===410){await env.DB.prepare("DELETE FROM subscriptions WHERE id=?").bind(row.id).run();removed++;}
       else if(r.ok||r.status===201){sent++;}
       else {failed++;}
      }catch(e){failed++;}
    }
    return json({ok:true,sent,removed,failed});
   }
   return json({error:"Not found"},404);
  }catch(e){return json({error:String(e?.message||e)},500);}
 }
};
