/**
 * FireRisk Intelligence - Google Drive export web app.  ORIGIN: NEW (Hackathon).
 *
 * Runs inside YOUR Google account and answers ONLY requests that carry FIRERISK_TOKEN. Read-only: it never
 * changes, shares or deletes anything in your Drive.
 *   action "export"  - the spreadsheets in FILES as .xlsx, plus a LISTING of every file in the folder that holds
 *                      the operations sheet (and its sub-folders, e.g. "Video Uploaded"): names, types, sizes, dates.
 *   action "token"   - a short-lived (about 1 hour) read-only Drive access token, so the FireRisk app on your own
 *                      computer can download the listed survey videos directly from Google Drive (videos are too
 *                      large to pass through this script). The token is never stored by the app.
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
  if (req.action === 'token') {
    return json_({ ok: true, access_token: ScriptApp.getOAuthToken(), expires_in_s: 3000, scope: 'drive.readonly' });
  }
  const out = exportAll_();
  try { out.listing = listFolder_(); } catch (err) { out.listing_error = String(err); }
  return json_(out);
}

/** Every file under the folder(s) that contain the operations sheet, up to 3 levels of sub-folders. */
function listFolder_() {
  const files = [];
  const parents = DriveApp.getFileById(FILES.ops_data).getParents();
  while (parents.hasNext()) walk_(parents.next(), '', 0, files);
  return files;
}

function walk_(folder, path, depth, out) {
  const here = path ? path + '/' + folder.getName() : folder.getName();
  const it = folder.getFiles();
  while (it.hasNext()) {
    const f = it.next();
    out.push({ id: f.getId(), title: f.getName(), mime_type: f.getMimeType(), size: f.getSize(),
               created_time: f.getDateCreated().toISOString(), modified_time: f.getLastUpdated().toISOString(),
               folder: here });
  }
  if (depth >= 3) return;
  const sub = folder.getFolders();
  while (sub.hasNext()) walk_(sub.next(), here, depth + 1, out);
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
  const list = listFolder_();
  Logger.log('Files in the data folder: ' + list.length + ' (videos: ' +
             list.filter(function (x) { return x.mime_type.indexOf('video/') === 0; }).length + ')');
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
