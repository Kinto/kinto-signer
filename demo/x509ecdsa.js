//https://blog.engelke.com/2014/10/17/parsing-ber-and-der-encoded-asn-1-objects/
function berToJavaScript(byteArray) {
  var position = 0;

  var result = {};
  result.cls        = (byteArray[position] & 0xc0) / 64;
  result.structured = ((byteArray[position] & 0x20) === 0x20);
  result.tag        = getTag();
  var length        = getLength(); // As encoded, which may be special value 0
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
  result.raw = byteArray.subarray(0, result.byteLength); // May not be the whole input array
  return result;

  function getTag() {
    var tag = byteArray[0] & 0x1f;
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
    var length = 0;
    if (byteArray[position] < 0x80) {
      length = byteArray[position];
      position += 1;
    } else {
      var numberOfDigits = byteArray[position] & 0x7f;
      position += 1;
      length = 0;
      for (var i=0; i<numberOfDigits; i++) {
        length = length * 256 + byteArray[position];
        position += 1;
      }
    }
    return length;
  }
}

function berListToJavaScript(byteArray) {
  var result = new Array();
  var nextPosition = 0;
  while (nextPosition < byteArray.length) {
    var nextPiece = berToJavaScript(byteArray.subarray(nextPosition));
    result.push(nextPiece);
    nextPosition += nextPiece.byteLength;
  }
  return result;
}

function berBitStringValue(byteArray) {
  return {
    unusedBits: byteArray[0],
    bytes: byteArray.subarray(1)
  };
}

function berObjectIdentifierValue(byteArray) {
  var oid = Math.floor(byteArray[0] / 40) + "." + byteArray[0] % 40;
  var position = 1;
  while(position < byteArray.length) {
    var nextInteger = 0;
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
  if (asn1.cls !== 0 || asn1.tag !== 16 || !asn1.structured) {
    throw new Error("Bad algorithm identifier. Not a SEQUENCE.");
  }
  var pieces = berListToJavaScript(asn1.contents);
  if (pieces.length > 2) {
    throw new Error("Bad algorithm identifier. Contains too many child objects.");
  }
  var encodedAlgorithm = pieces[1];
  if (encodedAlgorithm.cls !== 0 || encodedAlgorithm.tag !== 6 || encodedAlgorithm.structured) {
    throw new Error("Bad algorithm identifier. Does not begin with an OBJECT IDENTIFIER.");
  }
  return berObjectIdentifierValue(encodedAlgorithm.contents);
}

function parseSubjectPublicKeyInfo(asn1) {
  if (asn1.cls !== 0 || asn1.tag !== 16 || !asn1.structured) {
    throw new Error("Bad SPKI. Not a SEQUENCE.");
  }
  var pieces = berListToJavaScript(asn1.contents);
  if (pieces.length !== 2) {
    throw new Error("Bad SubjectPublicKeyInfo. Wrong number of child objects.");
  }
  return {
    algorithm: parseAlgorithmIdentifier(pieces[0]),
    bits: berBitStringValue(pieces[1].contents)
  };
}

function parseX509ECDSACertificate(byteArray) {
  var asn1 = berToJavaScript(byteArray);
  if (asn1.cls !== 0 || asn1.tag !== 16 || !asn1.structured) {
    throw new Error("This can't be an X.509 certificate. Wrong data type.");
  }
  var pieces = berListToJavaScript(asn1.contents);
  if (pieces.length !== 3) {
    throw new Error("Certificate contains more than the three specified children.");
  }
  return parseECDSACertificate(pieces[0]);
}

function parseECDSACertificate(asn1) {
  if (asn1.cls !== 0 || asn1.tag !== 16 || !asn1.structured) {
    throw new Error("This can't be a ECDSA certificate. Wrong data type.");
  }
  var pieces = berListToJavaScript(asn1.contents);
  if (pieces.length < 6) {
    throw new Error("Bad certificate. There are fewer than the six required children.");
  }
  const publicKey = parseSubjectPublicKeyInfo(pieces[5]);
  const ECDSA_P384 = "1.3.132.0.34";
  if (publicKey.algorithm !== ECDSA_P384) {
    throw new Error(`Signature algorithm ${publicKey.algorithm} is not supported.`);
  }
  // Binary content is x04 + x + y
  const content = publicKey.bits.bytes.slice(1);
  const length = content.length;
  if (length * 8 != 384 * 2) {
    throw new Error(`Invalid key size (${length * 8} bits)`)
  }
  publicKey.x = content.slice(0, length/2);
  publicKey.y = content.slice(length/2);
  return {publicKey};
}
