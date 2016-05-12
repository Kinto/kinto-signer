/**
 * The content of this file mainly comes from Charles Engelke's blog articles:
 *
 *  - https://blog.engelke.com/2014/10/17/parsing-ber-and-der-encoded-asn-1-objects/
 *  - https://blog.engelke.com/2014/10/21/web-crypto-and-x-509-certificates/
 *
 * The snippets were adapted to parse an ECDSA P-384 certificate containing a
 * public key. In this case, a public key is a position on the elliptic curve: (`x`, `y`).
 *
 * His useful explanations were inlined in the code as comments.
 *
 * Usage:
 *
 *
 * ```js
 *   const pemChain = "-----BEGIN CERTIFICATE-----\n" +
 *                    "MIIC0DCCAlUCCQDh7ZXFZjOO+jAKBggqhkjOPQQDAjCB0DELMAkGA1UEBhMCVVMx\n" +
 *                    "...                                                             \n" +
 *                    "...                                                             \n" +
 *                    "WHFmvQ==\n"
 *                    "-----END CERTIFICATE-----\n";
 *
 *   const stripped = pemChain.split("\n").slice(1, -2).join("");
 *   const der = base64ToBinary(stripped);
 *   var certificate = parseX509ECDSACertificate(der);
 *   const jwk = {
 *     kty: "EC",
 *     crv: "P-384",
 *     x: binaryToBase64URL(certificate.publicKey.x),
 *     y: binaryToBase64URL(certificate.publicKey.y),
 *     ext: true,
 *   }
 * ```
 *
 * The code has some limitations:
 *
 * - Only one certificate is loaded from the PEM
 * - Only the public key is loaded
 * - Given bad data it may try to overrun the byteArray and crash
 * - If it includes numbers too big for JavaScript to represent exactly as a Number
 *   it can crash.
 *
 */



/**
 * Take a BER (or DER) encoded byte array (Uint8Array) and return a JavaScript
 * object with fields `cls` (class as integer value), `tag` (integer),
 * `structured` (boolean), `contents` (Uint8Array), `byteLength` (entire object
 * size) and `raw` which is the BER/DER encoded source data (for debugging).
 */
function berToJavaScript(byteArray) {
  const result = {};

  let position = 0;

  // The first two bits of the first byte are the object’s class.
  result.cls = (byteArray[position] & 0xc0) / 64;
  // The third bit of the first byte tells whether it is primitive (0) or structured (1).
  result.structured = ((byteArray[position] & 0x20) === 0x20);
  // The next 5 bits of the first byte are the object's tag.
  result.tag = getTag();
  // The next byte starts defining the length of the contents.
  const length = getLength(); // As encoded, which may be special value 0
  // If it is 0x80, the length is unknown, and the contents immediately follow,
  // trailed by two 0 bytes in a row.
  if (length === 0x80) {
    length = 0;
    while (byteArray[position + length] !== 0 || byteArray[position + length + 1] !== 0) {
      length += 1;
    }
    result.byteLength = position + length + 2;
    result.contents   = byteArray.subarray(position, position + length);
  } else {
    result.byteLength = position + length;
    result.contents   = byteArray.subarray(position, result.byteLength);
  }
  // The remaining length bytes are the contents if the length is non-zero.
  result.raw = byteArray.subarray(0, result.byteLength); // May not be the whole input array
  return result;

  function getTag() {
    // The remaining 5 bits of the first byte are the object’s tag, unless they are all 1.
    // In that case, the next one or more bytes give the tag value. Take each byte until
    // you encounter one with a leading 0 bit instead of a leading 1 bit.
    // Drop the first bit from each byte, and concatenate the remaining bits.
    // Interpret that result as an integer.
    let tag = byteArray[0] & 0x1f;
    position += 1;
    if (tag === 0x1f) {
      tag = 0;
      while (byteArray[position] >= 0x80) {
        tag = tag * 128 + byteArray[position] - 0x80;
        position += 1;
      }
      tag = tag * 128 + byteArray[position] - 0x80;
      position += 1;
    }
    return tag;
  }

  function getLength() {
    // The next byte starts defining the length of the contents.
    // If the value of the first byte is between 0 and 128 (exclusive) then that
    // value is the length. Otherwise, the value is 128 more than the number of bytes
    // containing the length, which is interpreted as a big-endian integer.
    let length = 0;
    if (byteArray[position] < 0x80) {
      length = byteArray[position];
      position += 1;
    } else {
      let numberOfDigits = byteArray[position] & 0x7f;
      position += 1;
      length = 0;
      for (let i=0; i<numberOfDigits; i++) {
        length = length * 256 + byteArray[position];
        position += 1;
      }
    }
    return length;
  }
}

function berListToJavaScript(byteArray) {
  // Start parsing at the beginning of the array, then at the first byte
  // following the first result, and so on, until the byte array is consumed,
  // returning an array containing each object.
  const result = new Array();
  let nextPosition = 0;
  while (nextPosition < byteArray.length) {
    const nextPiece = berToJavaScript(byteArray.subarray(nextPosition));
    result.push(nextPiece);
    nextPosition += nextPiece.byteLength;
  }
  return result;
}

function berBitStringValue(byteArray) {
  // The contents of BIT STRING consist of an initial byte giving the number
  // of bits to ignore, then a byte array containing all the bits.
  return {
    unusedBits: byteArray[0],
    bytes: byteArray.subarray(1)
  };
}

function berObjectIdentifierValue(byteArray) {
  // Object Identifiers (OIDs) are essentially sequences of non-negative integers
  // representing different kinds of objects. A common way of writing them is as
  // a list of integers with periods between them.
  // The list of integers is interpreted as a hierarchical tree. The first integer
  // is the master organization for the OID, which can assign the second integer
  // values to member organizations, and so on. For example, the OID for an
  // RSA signature with SHA-1 (a very common one) is 1.2.840.113549.1.1.5.

  // The first two integers are taken from the first byte: the integer division
  // of the first byte by 40, and the remainder of that division.
  let oid = Math.floor(byteArray[0] / 40) + "." + byteArray[0] % 40;
  let position = 1;
  // The remaining integers are represented as lists of bytes, where all the bytes
  // except the last ones have leading 1 bits. The leading bits are dropped and the
  //  remaining bits interpreted as a binary integer.
  while(position < byteArray.length) {
    let nextInteger = 0;
    while (byteArray[position] >= 0x80) {
      nextInteger = nextInteger * 0x80 + (byteArray[position] & 0x7f);
      position += 1;
    }
    nextInteger = nextInteger * 0x80 + byteArray[position];
    position += 1;
    oid += "." + nextInteger;
  }
  return oid;
}

function parseAlgorithmIdentifier(asn1) {
  /*

   AlgorithmIdentifier  ::=  SEQUENCE  {
        algorithm               OBJECT IDENTIFIER,
        parameters              ANY DEFINED BY algorithm OPTIONAL  }

  */
  if (asn1.cls !== 0 || asn1.tag !== 16 || !asn1.structured) {
    throw new Error("Bad algorithm identifier. Not a SEQUENCE.");
  }
  const pieces = berListToJavaScript(asn1.contents);
  if (pieces.length > 2) {
    throw new Error("Bad algorithm identifier. Contains too many child objects.");
  }
  const encodedAlgorithm = pieces[1];
  if (encodedAlgorithm.cls !== 0 || encodedAlgorithm.tag !== 6 || encodedAlgorithm.structured) {
    throw new Error("Bad algorithm identifier. Does not begin with an OBJECT IDENTIFIER.");
  }
  return berObjectIdentifierValue(encodedAlgorithm.contents);
}

function parseSubjectPublicKeyInfo(asn1) {
  /*

     SubjectPublicKeyInfo  ::=  SEQUENCE  {
        algorithm            AlgorithmIdentifier,
        subjectPublicKey     BIT STRING  }

  */
  if (asn1.cls !== 0 || asn1.tag !== 16 || !asn1.structured) {
    throw new Error("Bad SPKI. Not a SEQUENCE.");
  }
  const pieces = berListToJavaScript(asn1.contents);
  if (pieces.length !== 2) {
    throw new Error("Bad SubjectPublicKeyInfo. Wrong number of child objects.");
  }
  return {
    algorithm: parseAlgorithmIdentifier(pieces[0]),
    subjectPublicKey: berBitStringValue(pieces[1].contents)
  };
}

function parseX509ECDSACertificate(byteArray) {
  const asn1 = berToJavaScript(byteArray);
  if (asn1.cls !== 0 || asn1.tag !== 16 || !asn1.structured) {
    throw new Error("This can't be an X.509 certificate. Wrong data type.");
  }
  const pieces = berListToJavaScript(asn1.contents);
  if (pieces.length !== 3) {
    throw new Error("Certificate contains more than the three specified children.");
  }
  // XXX: take the first one only
  return parseECDSACertificate(pieces[0]);
}

function parseECDSACertificate(asn1) {
  if (asn1.cls !== 0 || asn1.tag !== 16 || !asn1.structured) {
    throw new Error("This can't be a ECDSA certificate. Wrong data type.");
  }
  const pieces = berListToJavaScript(asn1.contents);
  if (pieces.length < 6) {
    throw new Error("Bad certificate. There are fewer than the six required children.");
  }
  // Using the live parse of ASN.1 helps a lot to figure which piece contains
  // the interesting info.
  // See http://bit.ly/1ZF3UeK
  const publicKey = parseSubjectPublicKeyInfo(pieces[5]);

  const ECDSA_P384 = "1.3.132.0.34";
  if (publicKey.algorithm !== ECDSA_P384) {
    throw new Error(`Signature algorithm ${publicKey.algorithm} is not supported.`);
  }

  // The first bytes indicates the compression.
  const compression = publicKey.subjectPublicKey.bytes[0];
  if (compression !== 0x04) {
    throw new Error(`Unsupported compression type.`);
  }

  // The next bytes contain the elliptic point x and y.
  const content = publicKey.subjectPublicKey.bytes.subarray(1);
  // We make sure the key size is correct (384 bits for each coordinate)
  const length = content.length;
  if (length * 8 != 384 * 2) {
    throw new Error(`Invalid key size (${length * 8} bits)`)
  }
  // Split in half.
  publicKey.x = content.slice(0, length/2);
  publicKey.y = content.slice(length/2);

  // XXX: we ignore everything except the public key.
  return {publicKey};
}
