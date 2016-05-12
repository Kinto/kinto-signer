/**
 * The content of this file comes Mozilla Central repository.
 * https://hg.mozilla.org/mozilla-central/raw-file/3461f3cae78495f100a0f7d3d2e0b89292d3ec02/toolkit/modules/CanonicalJSON.jsm
 */

// import jsesc from "jsesc";

const CanonicalJSON = {
  stringify: function stringify(source) {
    // Array values.
    if (Array.isArray(source)) {
      const jsonArray = source.map(x => typeof x === "undefined" ? null : x);
      return `[${jsonArray.map(stringify).join(",")}]`;
    }
    // Leverage jsesc library, mainly for unicode escaping.
    const toJSON = (input) => jsesc(input, {lowercaseHex: true, json: true});

    if (typeof source !== "object" || source === null) {
      return toJSON(source);
    }

    // Dealing with objects, ordering keys.
    const sortedKeys = Object.keys(source).sort();
    const lastIndex = sortedKeys.length - 1;
    return sortedKeys.reduce((serial, key, index) => {
      const value = source[key];
      // JSON.stringify drops keys with an undefined value.
      if (typeof value === "undefined") {
        return serial;
      }
      const jsonValue = value && value.toJSON ? value.toJSON() : value;
      const suffix = index !== lastIndex ? "," : "";
      const escapedKey = toJSON(key);
      return serial + `${escapedKey}:${stringify(jsonValue)}${suffix}`;
    }, "{") + "}";
  }
};
