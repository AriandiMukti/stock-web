package com.bdm.saku;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.DhcpInfo;
import android.net.Uri;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.Bundle;
import android.widget.Toast;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.zip.GZIPInputStream;

/**
 * BDM Saku: satu WebView yang menampilkan assets/ (UI offline) dan data hasil
 * website/ekspor_hp.py. Halaman dimuat dari asal palsu https://app.bdm/ yang
 * seluruhnya dilayani dari dalam APK + penyimpanan internal -- tidak ada
 * permintaan jaringan sungguhan dari halaman.
 *
 * Sinkron (pasangannya website/kirim_hp.py) dikerjakan di sini, bukan di JS:
 * siaran UDP untuk menemukan laptop, lalu unduh satu file lewat HTTP lokal.
 */
public class MainActivity extends Activity {
    private static final String HOST = "app.bdm";
    private static final String ASAL = "https://" + HOST + "/";
    private static final int PORT_HTTP = 8765;
    private static final int PORT_CARI = 8766;
    private static final int WARNA_LATAR = 0xFF04060A;

    private WebView web;

    private File fileData() {
        return new File(getFilesDir(), "bdm_hp.json.gz");
    }

    private File fileApk() {
        return new File(getFilesDir(), "pembaruan.apk");
    }

    @SuppressWarnings("deprecation")
    private long versiSendiri() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).versionCode;
        } catch (Exception e) {
            return 0;
        }
    }

    /** Baca versi hanya jika nama paket dan penandatangan cocok dengan aplikasi ini. */
    @SuppressWarnings("deprecation")
    private long versiApkTerverifikasi(File file) {
        if (!file.isFile()) return 0;
        try {
            int flags = Build.VERSION.SDK_INT >= 28
                    ? PackageManager.GET_SIGNING_CERTIFICATES : PackageManager.GET_SIGNATURES;
            PackageManager manager = getPackageManager();
            PackageInfo calon = manager.getPackageArchiveInfo(file.getPath(), flags);
            if (calon == null || !getPackageName().equals(calon.packageName)) return 0;
            PackageInfo terpasang = manager.getPackageInfo(getPackageName(), flags);
            Signature[] pembaruan = penandatangan(calon);
            Signature[] sendiri = penandatangan(terpasang);
            if (pembaruan == null || sendiri == null || pembaruan.length == 0
                    || !new HashSet<>(Arrays.asList(pembaruan)).equals(new HashSet<>(Arrays.asList(sendiri)))) {
                return 0;
            }
            return Build.VERSION.SDK_INT >= 28 ? calon.getLongVersionCode() : calon.versionCode;
        } catch (Exception e) {
            return 0;
        }
    }

    @SuppressWarnings("deprecation")
    private Signature[] penandatangan(PackageInfo info) {
        if (Build.VERSION.SDK_INT >= 28) {
            return info.signingInfo == null ? null : info.signingInfo.getApkContentsSigners();
        }
        return info.signatures;
    }

    private long versiApkTerunduh() {
        return versiApkTerverifikasi(fileApk());
    }

    @Override
    protected void onCreate(Bundle simpanan) {
        super.onCreate(simpanan);
        getWindow().setStatusBarColor(WARNA_LATAR);
        getWindow().setNavigationBarColor(WARNA_LATAR);

        web = new WebView(this);
        web.setBackgroundColor(WARNA_LATAR);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);

        web.addJavascriptInterface(new Jembatan(), "Android");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest r) {
                return layani(r.getUrl());
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                if (HOST.equals(u.getHost())) return false;
                // Tautan keluar (mis. post Stockbit di Ramai Dibahas) dibuka di browser HP.
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, u));
                } catch (Exception ignored) {
                }
                return true;
            }
        });

        // Sesudah pembaruan terpasang, file APK-nya tidak berguna lagi.
        if (fileApk().exists() && versiApkTerunduh() <= versiSendiri()) fileApk().delete();

        if (simpanan == null || web.restoreState(simpanan) == null) {
            web.loadUrl(ASAL + "index.html#/ringkasan");
        }
    }

    private void pasangPembaruan() {
        File f = fileApk();
        try {
            if (versiApkTerverifikasi(f) <= versiSendiri()) {
                throw new IOException("Paket, versi, atau tanda tangan pembaruan tidak cocok");
            }
            PackageInstaller pi = getPackageManager().getPackageInstaller();
            PackageInstaller.SessionParams p = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
            p.setAppPackageName(getPackageName());
            int id = pi.createSession(p);
            try (PackageInstaller.Session s = pi.openSession(id)) {
                try (InputStream in = new FileInputStream(f); OutputStream out = s.openWrite("bdm-saku", 0, f.length())) {
                    byte[] buf = new byte[65536];
                    int n;
                    while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
                    s.fsync(out);
                }
                Intent hasil = new Intent(this, InstallResultActivity.class);
                int flag = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
                s.commit(PendingIntent.getActivity(this, id, hasil, flag).getIntentSender());
            }
        } catch (Exception e) {
            final String pesan = "Pembaruan gagal: " + e.getMessage();
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    Toast.makeText(MainActivity.this, pesan, Toast.LENGTH_LONG).show();
                }
            });
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle keluar) {
        super.onSaveInstanceState(keluar);
        web.saveState(keluar);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    // ------------------------------------------------------------ pelayan halaman

    private WebResourceResponse layani(Uri u) {
        if (!HOST.equals(u.getHost())) {
            // Apa pun di luar app.bdm diblok: halaman ini tidak boleh menyentuh jaringan.
            return kosong(403);
        }
        String p = u.getPath();
        if (p == null || p.equals("/")) p = "/index.html";

        Map<String, String> kepala = new HashMap<>();
        kepala.put("Cache-Control", "no-store");
        try {
            if (p.equals("/data.json")) {
                File f = fileData();
                if (!f.exists()) return kosong(404);
                return new WebResourceResponse("application/json", "utf-8", 200, "OK", kepala,
                        new GZIPInputStream(new FileInputStream(f)));
            }
            String nama = p.substring(1);
            if (nama.contains("..")) return kosong(404);
            return new WebResourceResponse(jenis(nama), "utf-8", 200, "OK", kepala, getAssets().open(nama));
        } catch (IOException e) {
            return kosong(404);
        }
    }

    private static WebResourceResponse kosong(int status) {
        return new WebResourceResponse("text/plain", "utf-8", status, status == 404 ? "Not Found" : "Forbidden",
                new HashMap<String, String>(), new ByteArrayInputStream(new byte[0]));
    }

    private static String jenis(String nama) {
        if (nama.endsWith(".html")) return "text/html";
        if (nama.endsWith(".js")) return "application/javascript";
        if (nama.endsWith(".css")) return "text/css";
        if (nama.endsWith(".png")) return "image/png";
        if (nama.endsWith(".svg")) return "image/svg+xml";
        return "application/octet-stream";
    }

    // ------------------------------------------------------------ sinkron

    private class Jembatan {
        @JavascriptInterface
        public void sinkron(final String alamat, final String kode) {
            new Thread(new Runnable() {
                @Override
                public void run() {
                    jalankanSinkron(alamat == null ? "" : alamat.trim(), kode == null ? "" : kode.trim());
                }
            }).start();
        }

        @JavascriptInterface
        public boolean adaPembaruan() {
            return versiApkTerunduh() > versiSendiri();
        }

        @JavascriptInterface
        public void pasangPembaruan() {
            new Thread(new Runnable() {
                @Override
                public void run() {
                    MainActivity.this.pasangPembaruan();
                }
            }).start();
        }
    }

    private void jalankanSinkron(String alamat, String kode) {
        try {
            String host = alamat;
            if (host.isEmpty()) {
                host = cariLaptop();
                if (host == null) return;
            }
            JSONObject info;
            try {
                info = ambilInfo(host, kode);
            } catch (IOException e) {
                if (alamat.isEmpty()) throw e;
                // Alamat tersimpan bisa basi (IP laptop ganti dari DHCP) -- coba cari ulang sekali.
                kabar("info", "Tidak tersambung ke " + alamat + ", mencari ulang…", null);
                host = cariLaptop();
                if (host == null) return;
                info = ambilInfo(host, kode);
            }
            if (info == null) return;

            kabar("info", String.format("Mengunduh data %s (%.1f MB)…", info.optString("diubah"),
                    info.optLong("ukuran") / 1e6), null);
            unduh(host, kode, "/data", fileData(), true);

            // APK di laptop lebih baru dari yang terpasang: ikut diunduh, dipasang
            // nanti lewat tombol di Ringkasan (Android tetap minta konfirmasi).
            long versiLaptop = info.optLong("apk_versi", 0);
            if (versiLaptop > versiSendiri() && versiLaptop > versiApkTerunduh()) {
                kabar("info", "Mengunduh versi baru aplikasi…", null);
                unduh(host, kode, "/apk", fileApk(), false);
            }
            kabar("selesai", versiApkTerunduh() > versiSendiri()
                    ? "Selesai — data diperbarui. Versi baru aplikasi siap dipasang."
                    : "Selesai — data diperbarui.", null);
        } catch (SocketTimeoutException e) {
            kabar("galat", "Laptop tidak menjawab. Cek HP & laptop di WiFi yang sama, dan izinkan Python di firewall Windows (jaringan Private).", null);
        } catch (IOException e) {
            kabar("galat", "Gagal tersambung: " + e.getMessage(), null);
        } catch (Exception e) {
            kabar("galat", "Galat: " + e, null);
        }
    }

    private String basis(String host) {
        return "http://" + (host.contains(":") ? host : host + ":" + PORT_HTTP);
    }

    private HttpURLConnection buka(String url, String kode) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setInstanceFollowRedirects(false);
        c.setConnectTimeout(4000);
        c.setReadTimeout(30000);
        c.setRequestProperty("X-BDM-Kode", kode);
        return c;
    }

    /** null = sudah dilaporkan sebagai galat ke halaman. */
    private JSONObject ambilInfo(String host, String kode) throws Exception {
        HttpURLConnection c = buka(basis(host) + "/info", kode);
        try {
            int st = c.getResponseCode();
            if (st == 403) {
                kabar("galat", "Kode pasangan salah — lihat kode di jendela KIRIM_KE_HP di laptop.", null);
                return null;
            }
            if (st == 404) {
                kabar("galat", "Laptop belum punya file ekspor.", null);
                return null;
            }
            if (st != 200) throw new IOException("HTTP " + st);
            return new JSONObject(bacaTeks(c.getInputStream()));
        } finally {
            c.disconnect();
        }
    }

    private void unduh(String host, String kode, String jalur, File tujuan, boolean gzip) throws IOException {
        File sementara = File.createTempFile("unduhan-", gzip ? ".tmp" : ".apk", getFilesDir());
        try {
            HttpURLConnection c = buka(basis(host) + jalur, kode);
            try {
                if (c.getResponseCode() != 200) throw new IOException("HTTP " + c.getResponseCode());
                try (InputStream in = c.getInputStream(); OutputStream out = new FileOutputStream(sementara)) {
                    byte[] buf = new byte[65536];
                    int n;
                    while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
                }
            } finally {
                c.disconnect();
            }
            if (gzip) {
                try (InputStream gz = new GZIPInputStream(new FileInputStream(sementara))) {
                    byte[] buf = new byte[65536];
                    while (gz.read(buf) > 0) { }
                } catch (IOException e) {
                    throw new IOException("File data rusak saat diunduh, coba lagi", e);
                }
            } else if (versiApkTerverifikasi(sementara) <= versiSendiri()) {
                throw new IOException("Paket, versi, atau tanda tangan APK unduhan tidak cocok");
            }
            if (!sementara.renameTo(tujuan)) throw new IOException("Gagal menyimpan unduhan");
        } finally {
            sementara.delete();
        }
    }

    /** Siarkan BDM-CARI, kembalikan "ip:port" laptop, atau null (sudah dilaporkan). */
    private String cariLaptop() throws Exception {
        kabar("info", "Mencari laptop di WiFi…", null);
        byte[] pesan = "BDM-CARI".getBytes("UTF-8");
        try (DatagramSocket s = new DatagramSocket()) {
            s.setBroadcast(true);
            s.setSoTimeout(1200);
            for (int coba = 0; coba < 3; coba++) {
                for (InetAddress tujuan : alamatSiaran()) {
                    try {
                        s.send(new DatagramPacket(pesan, pesan.length, tujuan, PORT_CARI));
                    } catch (IOException ignored) {
                    }
                }
                try {
                    byte[] buf = new byte[128];
                    DatagramPacket p = new DatagramPacket(buf, buf.length);
                    s.receive(p);
                    String[] jawab = new String(p.getData(), 0, p.getLength(), "UTF-8").trim().split(" ");
                    if (jawab.length >= 2 && jawab[0].equals("BDM-ADA")) {
                        String host = p.getAddress().getHostAddress() + ":" + jawab[1];
                        kabar("alamat", "Ketemu " + (jawab.length > 2 ? jawab[2] : "laptop") + " di " + host, host);
                        return host;
                    }
                } catch (SocketTimeoutException ignored) {
                }
            }
        }
        kabar("galat", "Laptop tidak ketemu. Pastikan KIRIM_KE_HP.bat sedang jalan dan HP di WiFi yang sama — "
                + "atau ketik alamat IP yang tampil di layar laptop.", null);
        return null;
    }

    /** Siaran subnet WiFi (lebih andal di banyak router) + siaran umum. */
    private InetAddress[] alamatSiaran() throws IOException {
        InetAddress umum = InetAddress.getByName("255.255.255.255");
        try {
            WifiManager wm = (WifiManager) getApplicationContext().getSystemService(WIFI_SERVICE);
            DhcpInfo d = wm == null ? null : wm.getDhcpInfo();
            if (d != null && d.ipAddress != 0 && d.netmask != 0) {
                int b = (d.ipAddress & d.netmask) | ~d.netmask;
                byte[] q = new byte[4];
                for (int i = 0; i < 4; i++) q[i] = (byte) (b >> (i * 8));
                return new InetAddress[]{InetAddress.getByAddress(q), umum};
            }
        } catch (Exception ignored) {
        }
        return new InetAddress[]{umum};
    }

    private static String bacaTeks(InputStream in) throws IOException {
        java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        return out.toString("UTF-8");
    }

    private void kabar(String tahap, String pesan, String alamat) {
        final JSONObject o = new JSONObject();
        try {
            o.put("tahap", tahap);
            o.put("pesan", pesan);
            if (alamat != null) o.put("alamat", alamat);
        } catch (Exception ignored) {
        }
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                web.evaluateJavascript("window.bdmSinkron && window.bdmSinkron(" + o + ")", null);
            }
        });
    }
}
