function log(message) {
  const li = document.createElement("li");
  li.appendChild(document.createTextNode(message));
  document.body.appendChild(li);
}


function main() {
  const kinto = new Kinto({
    remote: "https://kinto-reader.dev.mozaws.net/v1",
    bucket: "blocklists"
  });
  const collection = kinto.collection("certificates", { hooks : {
    "incoming-changes": [validateCollectionSignature]
  }});

  log("Start a sync");
  collection.sync();

  function validateCollectionSignature(payload, collection) {
    let certChain;
    let collectionSignature;
    log("Fetch current signature");
    return fetchCollectionMetadata(collection)
      .then(({x5u, signature}) => {
        collectionSignature = signature;
        log("Fetch public certificate");
        return fetch(x5u).then((res) => res.text()).then((text) => { certChain = text; });
      })
      .then(() => {
        log("Load local records");
        return collection.list().then((result) => result.data)
          .then((localRecords) => mergeChanges(localRecords, payload.changes));
      })
      .then((merged) => {
        log("Serialize records canonically");
        return CanonicalJSON.stringify(merged);
      })
      .then((serialized) => verifyContentSignature(serialized, collectionSignature, certChain))
      .then((success) => {
        if (success) {
          log("Signature verification success.")
          return payload;
        }
        log("Signature verification failed!")
        throw new Error("Invalid signature");
      })
      .catch((error) => {
        console.error(error);
        log(error.message);
        throw error;
      });
  }

  function fetchCollectionMetadata(collection) {
    return collection.api
      .bucket(collection.bucket).collection(collection.name)
      .getMetadata()
      .then(result => result.signature);
  }

  function mergeChanges(localRecords, changes) {
    log("Merge incoming changes with local records");
    const records = {};
    // Kinto.js adds attributes to local records that aren"t present on server.
    // (e.g. _status)
    const stripPrivateProps = (obj) => {
      return Object.keys(obj).reduce((current, key) => {
        if (key.indexOf("_") !== 0) {
          current[key] = obj[key];
        }
        return current;
      }, {});
    };
    // Local records by id.
    localRecords.forEach((record) => records[record.id] = stripPrivateProps(record));
    // All existing records are replaced by the version from the server.
    changes.forEach((record) => records[record.id] = record);

    return Object.values(records)
      // Filter out deleted records.
      .filter((record) => record.deleted != true)
      // Sort list by record id.
      .sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  }

  function verifyContentSignature(text, signature, certChain) {
    log("Verify signature of synchronized records");
    return loadKey(certChain)
      .then(publicKey => verify(signature, text, publicKey));
  }
}

window.addEventListener("DOMContentLoaded", main);
