import { generateKeyPairSync } from "node:crypto";
const {publicKey,privateKey}=generateKeyPairSync("ec",{namedCurve:"prime256v1"});
const pub=publicKey.export({format:"jwk"}); const priv=privateKey.export({format:"jwk"});
const b64=s=>Buffer.from(s,"base64url").toString("base64url");
console.log(JSON.stringify({publicKey:b64(pub.x),privateKey:b64(priv.d)},null,2));
