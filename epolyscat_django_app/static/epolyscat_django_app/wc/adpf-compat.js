/**
 * Compatibility shim for the vendored pre-rebuild adpf web components
 * (adpf.min.js). Must be loaded BEFORE adpf.min.js.
 *
 * The rebuilt portal's REST API emits proto-native snake_case JSON
 * (e.g. compute_host_id), while the pre-rebuild adpf components read the old
 * DRF-era camelCase names (computeHostId). The components fetch through
 * window.fetch, so this wraps it and recursively adds camelCase aliases to
 * every JSON object returned from /api/ endpoints. Aliases are additive: the
 * snake_case keys stay, so shape-agnostic consumers are unaffected.
 *
 * The ePolyScat app's own frontend uses axios (XHR), which bypasses fetch —
 * this shim only affects the adpf components.
 */
(function () {
  "use strict";

  var originalFetch = window.fetch.bind(window);

  function snakeToCamel(key) {
    return key.replace(/_([a-z0-9])/g, function (_, c) {
      return c.toUpperCase();
    });
  }

  function addCamelAliases(value) {
    if (Array.isArray(value)) {
      for (var i = 0; i < value.length; i++) addCamelAliases(value[i]);
      return value;
    }
    if (value !== null && typeof value === "object") {
      var keys = Object.keys(value);
      for (var j = 0; j < keys.length; j++) {
        var key = keys[j];
        addCamelAliases(value[key]);
        var camel = snakeToCamel(key);
        if (camel !== key && !(camel in value)) {
          value[camel] = value[key];
        }
      }
    }
    return value;
  }

  window.fetch = function (input, init) {
    return originalFetch(input, init).then(function (response) {
      var url =
        typeof input === "string" ? input : (input && input.url) || "";
      if (url.indexOf("/api/") === -1) return response;
      var contentType = response.headers.get("content-type") || "";
      if (contentType.indexOf("json") === -1) return response;

      return response
        .clone()
        .json()
        .then(function (data) {
          var body = JSON.stringify(addCamelAliases(data));
          return new Response(body, {
            status: response.status,
            statusText: response.statusText,
            headers: response.headers,
          });
        })
        .catch(function () {
          // Body wasn't valid JSON after all — hand back the original.
          return response;
        });
    });
  };
})();
