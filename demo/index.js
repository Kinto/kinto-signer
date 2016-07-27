function log(message) {
  const li = document.createElement("li");
  li.appendChild(document.createTextNode(message));
  document.body.appendChild(li);
}


function sync() {
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
    log("Load local records");
    return Promise.all([
        collection.list().then((result) => result.data)
          .then((localRecords) => mergeChanges(localRecords, payload))
          .then((merged) => {
            log(`Serialize ${merged.data.length} records canonically`);
            return CanonicalJSON.stringify(merged);
          }),
        fetchCollectionMetadata(collection)
         .then(({signature}) => {
           log("Import the public key");
           const certChain = document.getElementById("certificate").value;
           return loadKey(certChain)
             .then((publicKey) => {return {publicKey, signature}});
         })
      ])
      .then(([serialized, {publicKey, signature}]) => {
        log("Verify signature of synchronized records");
        return verify(signature, serialized, publicKey);
      })
      .then((success) => {
        if (success) {
          log("→ Signature verification success.")
          return payload;
        }
        throw new Error("Signature verification failed!");
      })
      .catch((error) => {
        console.error(error);
        log(`✘ ${error.message}`);
        throw error;
      });
  }

  function fetchCollectionMetadata(collection) {
    log(`Fetch signature of collection ${collection.bucket}/${collection.name}`);
    return collection.api
      .bucket(collection.bucket).collection(collection.name)
      .getMetadata()
      .then(result => result.signature);
  }

  function mergeChanges(localRecords, payload) {
    log(`Merge ${payload.changes.length} incoming changes with ${localRecords.length} local records`);
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
    payload.changes.forEach((record) => records[record.id] = record);

    // Object.values()
    const values = [];
    for (let key in records) {
      values.push(records[key]);
    }

    const sortedRecords = values
      // Filter out deleted records.
      .filter((record) => record.deleted != true)
      // Sort list by record id.
      .sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);

    return {
      data: sortedRecords,
      last_modified: `${payload.lastModified}`
    }
  }
}

window.addEventListener("DOMContentLoaded", () => {
  document.getElementById("sync").addEventListener("click", sync);
});
