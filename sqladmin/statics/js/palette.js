// Command palette - click-driven, no keyboard shortcuts.
//
// Behaviour:
//   - The sidebar search trigger ([data-sa-palette-open]) opens the modal.
//   - Typing filters models (registry, no DB) and, at >= 2 chars, records.
//   - Clicking a model row navigates to its list page.
//   - Clicking "Search inside" scopes into one model; records then come from
//     that model only (one query). The chip's x clears the scope.
//   - Clicking a record opens its details page.
//   - The x button or the backdrop closes the modal.
//
// Endpoint contract (GET window.SA_PALETTE_URL):
//   ?q=<term>            -> { models:[...], records:[...], scope:null }
//   ?q=<term>&scope=<id> -> { models:[],    records:[...], scope:"<id>" }

var saPaletteScope = null;
var saPaletteScopeName = null;
var saPaletteTimeout = null;

function saPaletteText(key) {
  var i18n = window.SA_PALETTE_I18N || {};
  return i18n[key] || "";
}

// Substitute {name} style placeholders so translators control word order.
function saPaletteFormat(key, params) {
  var text = saPaletteText(key);
  for (var name in params) {
    if (Object.prototype.hasOwnProperty.call(params, name)) {
      text = text.split("{" + name + "}").join(params[name]);
    }
  }
  return text;
}

function saPaletteEsc(value) {
  return $("<div>").text(value == null ? "" : value).html();
}

// Wrap occurrences of the search term in <mark>.
// Splits the RAW text and escapes each piece separately: escaping first and
// then replacing would happily inject a tag inside an entity like &lt;.
function saPaletteHighlight(text, term) {
  text = String(text == null ? "" : text);
  if (!term) {
    return saPaletteEsc(text);
  }
  var needle = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  var re = new RegExp(needle, "gi");
  var out = "";
  var last = 0;
  var match;
  while ((match = re.exec(text)) !== null) {
    if (match[0].length === 0) {
      re.lastIndex++;
      continue;
    }
    out += saPaletteEsc(text.slice(last, match.index));
    out += '<mark class="sa-mark">' + saPaletteEsc(match[0]) + "</mark>";
    last = match.index + match[0].length;
  }
  return out + saPaletteEsc(text.slice(last));
}

function saPaletteTerm() {
  return ($("#sa-palette-input").val() || "").trim();
}

function saPaletteSingular(name) {
  if (/ies$/.test(name)) {
    return name.slice(0, -3) + "y";
  }
  if (/s$/.test(name)) {
    return name.slice(0, -1);
  }
  return name;
}

function saPaletteRow(lead, label, right, attrs) {
  return (
    '<div class="sa-row" ' + (attrs || "") + ">" +
    '<span class="sa-lead" aria-hidden="true">' + lead + "</span>" +
    '<span class="sa-label">' + label + "</span>" +
    '<span class="sa-right">' + (right || "") + "</span></div>"
  );
}

function saPaletteHead(title, tag) {
  return (
    '<div class="sa-ghead">' + saPaletteEsc(title) +
    (tag ? '<span class="sa-tag">' + saPaletteEsc(tag) + "</span>" : "") +
    "</div>"
  );
}

function saPaletteOpen() {
  $("#sa-palette").addClass("sa-open").attr("aria-hidden", "false");
  $("#sa-palette-input").val("");
  saPaletteSetScope(null, null);
  setTimeout(function () {
    $("#sa-palette-input").trigger("focus");
  }, 50);
}

function saPaletteClose() {
  $("#sa-palette").removeClass("sa-open").attr("aria-hidden", "true");
  $("#sa-palette-input").val("");
  saPaletteScope = null;
  saPaletteScopeName = null;
  $("#sa-palette-chip").empty();
  $("#sa-palette-results").empty();
}

function saPaletteSetScope(identity, name) {
  saPaletteScope = identity;
  saPaletteScopeName = name || null;

  if (saPaletteScope) {
    $("#sa-palette-chip").html(
      '<span class="sa-chip">' + saPaletteEsc(saPaletteScopeName || saPaletteScope) +
      '<span class="sa-x" data-clear="1" role="button">&times;</span></span>'
    );
    $("#sa-palette-input").attr(
      "placeholder",
      saPaletteFormat("searchInsidePlaceholder", {
        name: saPaletteScopeName || saPaletteScope
      })
    );
  } else {
    $("#sa-palette-chip").empty();
    $("#sa-palette-input").attr("placeholder", saPaletteText("searchPlaceholder"));
  }

  saPaletteFetch();
  $("#sa-palette-input").trigger("focus");
}

function saPaletteFetch() {
  // Native trim: jQuery 4.0 removed $.trim.
  var term = ($("#sa-palette-input").val() || "").trim();
  $.ajax({
    url: window.SA_PALETTE_URL,
    method: "GET",
    dataType: "json",
    data: saPaletteScope ? { q: term, scope: saPaletteScope } : { q: term },
    headers: { "X-Requested-With": "XMLHttpRequest" },
    success: saPaletteRender,
    error: function () {
      $("#sa-palette-results").html(
        '<div class="sa-empty">' + saPaletteEsc(saPaletteText("searchFailed")) + "</div>"
      );
    }
  });
}

function saPaletteRender(data) {
  var html = "";
  var term = saPaletteTerm();

  if (data.scope) {
    html += saPaletteHead(
      saPaletteFormat("recordsIn", { name: saPaletteScopeName || data.scope }),
      saPaletteText("oneQuery")
    );
    if (data.records.length) {
      $.each(data.records, function (i, r) {
        html += saPaletteRow(
          "&#9636;",
          '<span class="sa-pk">' + saPaletteEsc(r.pk) + "</span> " +
            saPaletteHighlight(r.label, term),
          '<span class="sa-badge">' + saPaletteEsc(saPaletteText("open")) + "</span>",
          'data-url="' + saPaletteEsc(r.url) + '"'
        );
      });
    } else {
      html += '<div class="sa-empty">' + saPaletteEsc(saPaletteText("noMatches")) + "</div>";
    }
  } else {
    var models = data.models || [];
    if (models.length) {
      html += saPaletteHead(saPaletteText("models"), saPaletteText("modelsHint"));
      $.each(models.slice(0, 6), function (i, m) {
        var right = m.searchable
          ? '<button type="button" class="sa-scopebtn" data-scope="' + saPaletteEsc(m.identity) +
            '" data-name="' + saPaletteEsc(m.name) + '">' +
            saPaletteEsc(saPaletteText("searchInside")) + "</button>"
          : "";
        html += saPaletteRow(
          "&#9638;",
          saPaletteHighlight(m.name, term) +
            (m.category
              ? ' <span class="sa-pk" style="font-size:12px">&middot; ' + saPaletteEsc(m.category) + "</span>"
              : ""),
          right,
          'data-url="' + saPaletteEsc(m.url) + '"'
        );
      });
      if (models.length > 6) {
        html += '<div class="sa-empty" style="padding:6px 15px 8px;text-align:left">' +
          saPaletteEsc(saPaletteFormat("more", { count: models.length - 6 })) + "</div>";
      }

    }

    // Commands come from the server (ModelView.palette_commands), so they
    // follow the best-matching model rather than a hardcoded first entry.
    var cmds = data.commands || [];
    if (cmds.length) {
      html += saPaletteHead(saPaletteText("commands"), "");
      $.each(cmds, function (i, cmd) {
        var label = (cmd.label === "goTo" || cmd.label === "create")
          ? saPaletteFormat(cmd.label, { name: cmd.name })
          : cmd.label;
        var badge = cmd.badge
          ? '<span class="sa-badge">' + saPaletteEsc(saPaletteText(cmd.badge) || cmd.badge) + "</span>"
          : "";
        html += saPaletteRow(
          '<span class="sa-cmdico">' + saPaletteEsc(cmd.icon || "\u203a") + "</span>",
          saPaletteEsc(label),
          badge,
          'data-url="' + saPaletteEsc(cmd.url) + '"'
        );
      });
    }

    var recs = data.records || [];
    if (recs.length) {
      html += saPaletteHead(saPaletteText("records"), "");
      $.each(recs, function (i, r) {
        html += saPaletteRow(
          "&#9673;",
          '<span class="sa-pk">' + saPaletteEsc(r.pk) + "</span> " +
            saPaletteHighlight(r.label, term),
          '<span class="sa-badge">' + saPaletteEsc(r.model_name) + "</span>",
          'data-url="' + saPaletteEsc(r.url) + '"'
        );
      });
    }

    if (!html) {
      html = '<div class="sa-empty">' + saPaletteEsc(saPaletteText("nothingFound")) + "</div>";
    }
  }

  $("#sa-palette-results").html(html);
}

// Open
$(document).on("click", "[data-sa-palette-open]", function (e) {
  e.preventDefault();
  saPaletteOpen();
});

// Close (button or backdrop)
$(document).on("click", "#sa-palette-close", function () {
  saPaletteClose();
});
$(document).on("click", "#sa-palette", function (e) {
  if (e.target === this) {
    saPaletteClose();
  }
});

// Clear scope
$(document).on("click", "#sa-palette-chip [data-clear]", function () {
  saPaletteSetScope(null, null);
});

// Scope into a model
$(document).on("click", "#sa-palette-results [data-scope]", function (e) {
  e.stopPropagation();
  saPaletteSetScope($(this).data("scope"), $(this).data("name"));
});

// Navigate (model / command / record)
$(document).on("click", "#sa-palette-results .sa-row", function () {
  var url = $(this).attr("data-url");
  if (url) {
    window.location.href = url;
  }
});

// Debounced search on input
$(document).on("input", "#sa-palette-input", function () {
  clearTimeout(saPaletteTimeout);
  saPaletteTimeout = setTimeout(saPaletteFetch, 150);
});