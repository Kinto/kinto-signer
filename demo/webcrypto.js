// import CanonicalJSON from "./canonicaljson";
// import parseX509ECDSACertificate from "./x509ecdsa";

function base64ToBinary(base64) {
  var binary_string =  window.atob(base64);
  var len = binary_string.length;
  var bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binary_string.charCodeAt(i);
  }
  return bytes;
}

function binaryToBase64URL(int8Array) {
  return window.btoa(String.fromCharCode.apply(null, int8Array))
               .replace(/\+/g, '-').replace(/\//g, '_')  // URL friendly
               .replace(/\=+$/, '');  // No padding.
}

/**

 * Load an existing key.
 *
 * @param {Object} pemChain - The key, in its PEM form.
 * @returns {Promise}     - A promise that will resolve with the CryptoKey object.
 **/
function loadKey(pemChain) {
  const stripped = pemChain.split("\n").slice(1, -2).join("");
  const der = base64ToBinary(stripped);
  var certificate = parseX509ECDSACertificate(der);  // x509ecdsa.js
  const jwk = {
    kty: "EC",
    crv: "P-384",
    x: binaryToBase64URL(certificate.publicKey.x),
    y: binaryToBase64URL(certificate.publicKey.y),
    ext: true,
  }
  const usages = ["verify"]; //"verify" for public key import, "sign" for private key imports
  return window.crypto.subtle.importKey("jwk", jwk, {
      name: "ECDSA",
      namedCurve: "P-384"
    },
    false, //whether the key is extractable (i.e. can be used in exportKey),
    usages
  );
}

/**
 * Verify the given signature validity given the data and public key.
 *
 * @param {String} signature - The signature in base64.
 * @param {String} data - The data, encoded as a string.
 * @param {CryptoKey} publicKey - The loaded CryptoKey object.
 **/
function verify(signature, data, publicKey) {
  const prefix = "Content-Signature:\x00";
  // from base64url to base64:
  const sigBase64 = signature.replace(/\-/g, '+').replace(/_/g, "\/");
  return window.crypto.subtle.verify({
      name: "ECDSA",
      hash: {name: "SHA-384"}
    },
    publicKey,
    base64ToBinary(sigBase64).buffer,
    new TextEncoder("utf-8").encode(prefix + data)
  );
}
