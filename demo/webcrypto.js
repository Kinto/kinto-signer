/**
 * Load an existing key.
 *
 * @param {Object} rawKey - The key, in its PEM form.
 * @returns {Promise} - A promise that will resolve in the CryptoKey object.
 **/
function loadKey(rawKey) {
  const stripped = rawKey.split("\n").slice(1, -2).join("");
  console.log(stripped);
  const binaryKey = base64ToArrayBuffer(stripped);
  const key = {
    kty: "EC",
    crv: "P-384",
    x: "zCQ5BPHPCLZYgdpo1n-x_90P2Ij52d53YVwTh3ZdiMo",
    y: "pDfQTUx0-OiZc5ZuKMcA7v2Q7ZPKsQwzB58bft0JTko",
    ext: true,
  }
  const usages = ["verify"]; //"verify" for public key import, "sign" for private key imports
  return window.crypto.subtle.importKey("jwt", binaryKey, {
      name: "ECDSA",
      namedCurve: {name: "P-384"}
    },
    false, //whether the key is extractable (i.e. can be used in exportKey),
    usages
  )
}

/**
 * Verify the given signature validity given the data and public key.
 *
 * @param {String} signature - The signature in base64.
 * @param {String} data - The data, encoded as a string.
 * @param {CryptoKey} publicKey - The loaded CryptoKey object.
 **/
function verify(signature, data, publicKey) {
  return window.crypto.subtle.verify({
      name: "ECDSA",
      hash: {name: "SHA-384"}
    },
    publicKey,
    base64ToArrayBuffer(signature),
    new TextEncoder("utf-8").encode(data)
  );
}

/**
 * Convert a base64 String into an Array Buffer.
 *
 * @param {String} base64 - A base64 string.
 * @returns {ArrayBuffer} - The Array Buffer representation of the given
 * string.
 **/
function base64ToArrayBuffer(base64) {
  var binary_string =  window.atob(base64);
  var len = binary_string.length;
  var bytes = new Uint8Array( len );
  for (var i = 0; i < len; i++)        {
      bytes[i] = binary_string.charCodeAt(i);
  }
  return bytes.buffer;
}
