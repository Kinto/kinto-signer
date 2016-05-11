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
