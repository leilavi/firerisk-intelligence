/**
 * FireRisk Intelligence - Google Drive export web app.  ORIGIN: NEW (Hackathon).
 *
 * Runs inside YOUR Google account. It reads ONLY the files listed in FILES and answers ONLY requests that
 * carry FIRERISK_TOKEN. It never changes, shares or deletes anything in your Drive.
 *
 * setup_drive_sync.bat fills in the two placeholders below and saves a ready-to-paste copy in
 * data/private/drive_sync/. Do not publish the filled-in copy.
 */
const FIRERISK_TOKEN = '__FIRERISK_TOKEN__';
const FILES = __FIRERISK_FILES__;   // {"ops_data": "<Drive file ID>", "vehicles": "<Drive file ID>"}

function doPost(e) {
  let req = {};
  try { req = JSON.parse(e.postData.contents); } catch (err) { req = {}; }
  if (!req.token || req.token !== FIRERISK_TOKEN) return json_({ ok: false, error: 'unauthorized' });
  return json_(exportAll_());
}

function doGet() {
  // No data without the token. Opening the URL in a browser only shows that the app is running.
  return json_({ ok: false, error: 'use POST with the token' });
}

function exportAll_() {
  const out = { ok: true, generated_at: new Date().toISOString(), files: {} };
  Object.keys(FILES).forEach(function (key) {
    const id = FILES[key];
    try {
      const file = DriveApp.getFileById(id);
      const mime = file.getMimeType();
      let bytes;
      if (mime === MimeType.GOOGLE_SHEETS) {
        const url = 'https://docs.google.com/spreadsheets/d/' + id + '/export?format=xlsx';
        const resp = UrlFetchApp.fetch(url, {
          headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() }, muteHttpExceptions: true });
        if (resp.getResponseCode() !== 200) throw new Error('export failed, HTTP ' + resp.getResponseCode());
        bytes = resp.getBlob().getBytes();
      } else {
        bytes = file.getBlob().getBytes();
      }
      out.files[key] = {
        title: file.getName(), drive_file_id: id, mime_type: mime,
        drive_modified_time: file.getLastUpdated().toISOString(),
        size: bytes.length, data_b64: Utilities.base64Encode(bytes) };
    } catch (err) {
      out.files[key] = { error: String(err) };
    }
  });
  return out;
}

/** Run this once from the editor (Run > testExport) to grant access and check the files. Logs sizes only. */
function testExport() {
  const r = exportAll_();
  Object.keys(r.files).forEach(function (k) {
    const f = r.files[k];
    Logger.log(k + ': ' + (f.error ? 'ERROR ' + f.error : f.title + ', ' + f.size + ' bytes, modified ' + f.drive_modified_time));
  });
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
