// Handle delete modal
$(document).on('shown.bs.modal', '#modal-delete', function (event) {
  var element = $(event.relatedTarget);

  var name = element.data("name");
  var pk = element.data("pk");
  $("#modal-delete-text").text("This will permanently delete " + name + " " + pk + "?");

  $("#modal-delete-button").attr("data-url", element.data("url"));
});

$(document).on('click', '#modal-delete-button', function () {
  $.ajax({
    url: $(this).attr('data-url'),
    method: 'DELETE',
    headers: {
      'Accept': 'text/html',
    },
    success: function (result) {
      window.location.href = result;
    },
    error: function (request) {
      const contentType = request.getResponseHeader('Content-Type') || '';

      if (contentType.includes('text/html')) {
        document.open();
        document.write(request.responseText);
        document.close();
      } else {
        alert(request.responseText);
      }
    }
  });
});

// Handle import modal
$(document).on('shown.bs.modal', '#modal-import', function (event) {
  const trigger = $(event.relatedTarget);
  const frm = $('#modal-import-form');
  const importUrl = trigger.data('url');

  if (importUrl) {
    frm.attr('action', importUrl);
  }

  $('#csvfile').val('');
  $('#csvfile-name').text('No file selected');
  $('#csvfile-button').removeClass('disabled').attr('aria-disabled', 'false');
  $('#continue-on-error').prop('checked', false);
  $('#modal-import-text').text('').attr('class', 'd-none');
  $('#modal-import-progress').addClass('d-none');
  $('#modal-import-progress-bar').css('width', '0%');
  $('#modal-import-progress-text').text('0/0 rows processed');
});

$(document).on('change', '#csvfile', function () {
  const fileInput = this;
  const file = fileInput && fileInput.files && fileInput.files.length ? fileInput.files[0] : null;
  $('#csvfile-name').text(file ? file.name : 'No file selected');
});

function setImportInputsDisabled(disabled) {
  $('#csvfile').prop('disabled', disabled);
  $('#continue-on-error').prop('disabled', disabled);
  $('#csvfile-button')
    .toggleClass('disabled', disabled)
    .attr('aria-disabled', disabled ? 'true' : 'false');
}

let missedRowsCsvUrl = null;
let missedRowsTxtUrl = null;
let activeImportController = null;
let importInProgress = false;
let persistingTickerId = null;
let persistingStartedAtMs = null;
let lastProgressSnapshot = { processed: 0, total: 0, imported: 0, skipped: 0 };

function stopPersistingTicker() {
  if (persistingTickerId) {
    clearInterval(persistingTickerId);
    persistingTickerId = null;
  }
  persistingStartedAtMs = null;
}

function renderPersistingProgressText() {
  if (persistingStartedAtMs == null) {
    return;
  }

  const elapsedSeconds = Math.max(
    0,
    Math.floor((Date.now() - persistingStartedAtMs) / 1000)
  );

  $('#modal-import-progress-text').text(
    lastProgressSnapshot.imported + ' imported, ' +
    lastProgressSnapshot.skipped + ' skipped, ' +
    lastProgressSnapshot.processed + '/' + lastProgressSnapshot.total +
    ' rows processed - saving valid rows... (' + elapsedSeconds + 's)'
  );
}

function startPersistingTicker(processed, total, imported, skipped) {
  lastProgressSnapshot = {
    processed: processed,
    total: total,
    imported: imported,
    skipped: skipped,
  };

  if (persistingTickerId) {
    return;
  }

  persistingStartedAtMs = Date.now();
  renderPersistingProgressText();
  persistingTickerId = setInterval(renderPersistingProgressText, 1000);
}

function updateImportProgress(processed, total, imported, skipped) {
  const safeTotal = total > 0 ? total : 1;
  const percentage = Math.min(100, Math.round((processed / safeTotal) * 100));
  const isPersistingPhase = arguments.length > 4 && arguments[4] === 'persisting';

  lastProgressSnapshot = {
    processed: processed,
    total: total,
    imported: imported,
    skipped: skipped,
  };

  $('#modal-import-progress').removeClass('d-none');
  $('#modal-import-progress-bar').css('width', percentage + '%');

  if (isPersistingPhase) {
    startPersistingTicker(processed, total, imported, skipped);
    return;
  }

  stopPersistingTicker();
  $('#modal-import-progress-text').text(
    imported + ' imported, ' + skipped + ' skipped, ' +
    processed + '/' + total + ' rows processed'
  );
}

function revokeMissedRowsUrls() {
  if (missedRowsCsvUrl) {
    URL.revokeObjectURL(missedRowsCsvUrl);
    missedRowsCsvUrl = null;
  }
  if (missedRowsTxtUrl) {
    URL.revokeObjectURL(missedRowsTxtUrl);
    missedRowsTxtUrl = null;
  }
}

function csvCell(value) {
  const text = value == null ? '' : String(value);
  return '"' + text.replace(/"/g, '""') + '"';
}

function buildMissedRowsCsv(missedRows) {
  if (!missedRows.length) {
    return '';
  }

  const dataColumns = Object.keys(missedRows[0].data || {});
  const header = ['line', 'errors'].concat(dataColumns);
  const lines = [header.map(csvCell).join(',')];

  missedRows.forEach(function (row) {
    const errorText = JSON.stringify(row.errors || {});
    const rowValues = [row.line, errorText];

    dataColumns.forEach(function (column) {
      rowValues.push((row.data || {})[column]);
    });

    lines.push(rowValues.map(csvCell).join(','));
  });

  return lines.join('\n');
}

function buildMissedRowsTxt(missedRows) {
  return missedRows.map(function (row) {
    return [
      'Line: ' + row.line,
      'Data: ' + JSON.stringify(row.data || {}),
      'Errors: ' + JSON.stringify(row.errors || {})
    ].join('\n');
  }).join('\n\n');
}

function createDownloadUrl(content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  return URL.createObjectURL(blob);
}

function updateMissedRowsDownloads(missedRows) {
  revokeMissedRowsUrls();

  if (!missedRows.length) {
    $('#modal-import-result-missed').addClass('d-none');
    $('#modal-import-download-csv').attr('href', '#');
    $('#modal-import-download-txt').attr('href', '#');
    return;
  }

  const csvContent = buildMissedRowsCsv(missedRows);
  const txtContent = buildMissedRowsTxt(missedRows);

  missedRowsCsvUrl = createDownloadUrl(csvContent, 'text/csv;charset=utf-8');
  missedRowsTxtUrl = createDownloadUrl(txtContent, 'text/plain;charset=utf-8');

  $('#modal-import-download-csv').attr('href', missedRowsCsvUrl);
  $('#modal-import-download-txt').attr('href', missedRowsTxtUrl);
  $('#modal-import-result-missed').removeClass('d-none');
}

function showImportResult(result) {
  const title = result.ok ? 'Import completed' : 'Import failed';
  const summary = result.summary || 'No summary available.';
  const missedRows = result.missed_rows || [];

  $('#modal-import-result-title').text(title);
  $('#modal-import-result-summary').text(summary);

  updateMissedRowsDownloads(missedRows);

  showModal('modal-import-result');
}

$('#modal-import-refresh').on('click', function () {
  window.location.reload();
});

$(document).on('hidden.bs.modal', '#modal-import-result', function () {
  revokeMissedRowsUrls();
});

$(document).on('hidden.bs.modal', '#modal-import', function () {
  if (importInProgress && activeImportController) {
    activeImportController.abort();
  }
});

$(document).on('click', '#modal-import-cancel', function () {
  if (importInProgress && activeImportController) {
    activeImportController.abort();
  }
});

$(document).on('submit', '#modal-import-form', function (e) {
  e.preventDefault();

  const frm = $(this);
  const submitButton = $('#modal-import-button');
  const csvInput = $('#csvfile')[0];
  const continueCheckbox = $('#continue-on-error');
  const file = csvInput && csvInput.files ? csvInput.files[0] : null;

  if (importInProgress) {
    return;
  }

  if (!file) {
    $('#modal-import-text').text('Please select a CSV file.').attr('class', 'alert alert-danger');
    return;
  }

  const formData = new FormData();
  formData.append('csvfile', file);
  formData.append('continue_on_error', $('#continue-on-error').is(':checked') ? '1' : '0');

  activeImportController = new AbortController();
  importInProgress = true;
  submitButton.prop('disabled', true);
  setImportInputsDisabled(true);
  stopPersistingTicker();
  updateImportProgress(0, 0, 0, 0);

  fetch(frm.attr('action'), {
    method: frm.attr('method'),
    body: formData,
    signal: activeImportController.signal,
    headers: {
      Accept: 'application/x-ndjson'
    }
  })
    .then(async function (response) {
      if (!response.ok || !response.body) {
        const message = await response.text();
        throw new Error(message || 'An error occurred while importing CSV.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let finalResult = null;

      while (true) {
        const chunk = await reader.read();
        if (chunk.done) {
          break;
        }

        buffer += decoder.decode(chunk.value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        lines.forEach(function (line) {
          if (!line.trim()) {
            return;
          }

          const event = JSON.parse(line);
          if (event.type === 'progress') {
            updateImportProgress(
              event.processed,
              event.total,
              event.imported,
              event.skipped,
              event.phase
            );
          } else if (event.type === 'result') {
            finalResult = event;
          }
        });
      }

      if (!finalResult) {
        throw new Error('Import did not return a final result.');
      }

      importInProgress = false;
      stopPersistingTicker();
      $('#modal-import').modal('hide');
      showImportResult(finalResult);
    })
    .catch(function (error) {
      if (error && error.name === 'AbortError') {
        $('#modal-import-text').text('Import canceled from browser. Server may still finalize in-flight work.');
        $('#modal-import-text').attr('class', 'alert alert-warning');
        return;
      }

      $('#modal-import-text').text(error.message || 'An error occurred while importing CSV.');
      $('#modal-import-text').attr('class', 'alert alert-danger');
    })
    .finally(function () {
      importInProgress = false;
      stopPersistingTicker();
      activeImportController = null;
      submitButton.prop('disabled', false);
      setImportInputsDisabled(false);
    });
});

// One-time secret modal
document.addEventListener('DOMContentLoaded', function () {
  var modalEl = document.getElementById('modal-secret');
  if (!modalEl) {
    return;
  }
  document.getElementById('modal-secret-trigger').click();
  var nextUrl = modalEl.dataset.nextUrl;
  if (nextUrl) {
    modalEl.addEventListener('hidden.bs.modal', function () {
      window.location.replace(nextUrl);
    });
  }
  var copyButton = document.getElementById('modal-secret-copy');
  var secretValueInput = document.getElementById('modal-secret-value');
  if (copyButton && secretValueInput) {
    copyButton.addEventListener('click', function () {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(secretValueInput.value);
      }
    });
  }
});

// Search
$(document).on('click', '#search-button', function () {
  var searchTerm = encodeURIComponent($("#search-input").val());

  newUrl = "";
  if (window.location.search && window.location.search.indexOf('search=') != -1) {
    newUrl = window.location.search.replace(/search=[^&]*/, "search=" + searchTerm);
  } else if (window.location.search) {
    newUrl = window.location.search + "&search=" + searchTerm;
  } else {
    newUrl = window.location.search + "?search=" + searchTerm;
  }
  window.location.href = newUrl;
});

// Reset search
$(document).on('click', '#search-reset', function () {
  if (window.location.search && window.location.search.indexOf('search=') != -1) {
    window.location.href = window.location.search.replace(/search=[^&]*/, "");
  }
});

// Press enter to search
$(document).on('keypress', '#search-input', function (e) {
  if (e.which === 13) {
    $('#search-button').trigger('click');
  }
});

// Init a timeout variable to be used below
var timeout = null;
// Search
$(document).on('keyup', '#search-input', function (e) {
  clearTimeout(timeout);
  if ($(this).data('searchAutoSubmit') === false) {
    return;
  }
  // Make a new timeout set to go off in 1000ms (1 second)
  timeout = setTimeout(function () {
    $('#search-button').trigger('click');
  }, 1000);
});

// Date picker
$(':input[data-role="datepicker"]:not([readonly])').each(function () {
  $(this).flatpickr({
    enableTime: false,
    allowInput: true,
    dateFormat: "Y-m-d",
  });
});

// DateTime picker
$(':input[data-role="datetimepicker"]:not([readonly])').each(function () {
  $(this).flatpickr({
    enableTime: true,
    allowInput: true,
    enableSeconds: true,
    time_24hr: true,
    dateFormat: "Y-m-d H:i:s",
  });
});

// Ajax Refs
$(':input[data-role="select2-ajax"]').each(function () {
  var $select = $(this);

  var allowBlank = !!$select.data("allowBlank");
  var isMultiple = !!$select.prop("multiple");
  var placeholderText = $select.attr("placeholder") || "Search";
  var originalName = $select.attr("name");

  var select2AjaxOptions = {
    minimumInputLength: 1,
    placeholder: placeholderText,
    ajax: {
      url: $select.data("url"),
      dataType: 'json',
      data: function (params) {
        return {
          name: originalName,
          term: params.term,
        }
      }
    }
  };

  if (allowBlank && !isMultiple) {
    select2AjaxOptions.allowClear = true;
  }

  $select.select2(select2AjaxOptions);

  var existing_data = $select.data("json") || [];
  existing_data.forEach(function (data) {
    var option = new Option(data.text, data.id, true, true);
    $select.append(option);
  });

  $select.trigger('change');
});


// Checkbox select
$("#select-all").on('click', function () {
  $('input.select-box:checkbox').prop('checked', this.checked);
});

function showModal(modalId) {
  var modalElement = document.getElementById(modalId);
  if (!modalElement) {
    return;
  }
  // Use Tabler bundled Bootstrap.
  window.tabler.bootstrap.Modal.getOrCreateInstance(modalElement).show();
}

// Bulk delete
$("#action-delete").on('click', function () {
  var pks = [];
  $('.select-box').each(function () {
    if ($(this).is(':checked')) {
      pks.push($(this).siblings().get(0).value);
    }
  });

  $('#action-delete').data("pk", pks);
  $('#action-delete').data("url", $(this).data('url') + '?pks=' + pks.join(","));
  showModal('modal-delete');
});

$("[id^='action-custom-']").on('click', function () {
  var pks = [];
  $('.select-box').each(function () {
    if ($(this).is(':checked')) {
      pks.push($(this).siblings().get(0).value);
    }
  });

  window.location.href = $(this).attr('data-url') + '?pks=' + pks.join(",");
});

// Select2 Tags
$(':input[data-role="select2-tags"]').each(function () {
  $(this).select2({
    tags: true,
    multiple: true,
  });

  existing_data = $(this).data("json") || [];
  for (var i = 0; i < existing_data.length; i++) {
    var option = new Option(existing_data[i], existing_data[i], true, true);
    $(this).append(option).trigger('change');
  }
});

function copyToClipboard(element, value) {
  navigator.clipboard.writeText(value)
    .then(() => {
      const alertElement = element.nextElementSibling;
      if (
        alertElement &&
        alertElement.classList.contains('alert') &&
        alertElement.classList.contains('alert-primary')
      ) {
        alertElement.classList.remove('fade');
        setTimeout(() => {
          alertElement.classList.add('fade');
        }, 2000);
      }
    })
    .catch(err => {
        console.error('Failed to copy text: ', err);
    });
}
