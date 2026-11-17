# Build BDM Saku tanpa Gradle/Android Studio -- langsung pakai build-tools SDK.
# Hasil: website\hp\BDM-Saku.apk
#
#   powershell -ExecutionPolicy Bypass -File build_apk.ps1
#
# Kunci tanda tangan (bdm-saku.keystore + .pass) dibuat sekali di folder ini.
# JANGAN dihapus: Android cuma mau memperbarui aplikasi yang ditandatangani
# kunci yang sama -- kunci baru berarti harus uninstall dulu (data di HP hilang).
param([switch]$Kandidat)

$ErrorActionPreference = 'Stop'

$SINI = $PSScriptRoot
$SDK = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { $env:ANDROID_SDK_ROOT }
if (-not $SDK -or -not $env:JAVA_HOME -or -not $env:FLASK_RUNTIME_DIR) {
    throw 'Set ANDROID_HOME (or ANDROID_SDK_ROOT), JAVA_HOME, and FLASK_RUNTIME_DIR first'
}
$BT   = Join-Path $SDK 'build-tools\35.0.0'
$JAR  = Join-Path $SDK 'platforms\android-36\android.jar'
$JDK = $env:JAVA_HOME
$runtimeRoot = [IO.Path]::GetFullPath($env:FLASK_RUNTIME_DIR)
$sourceRoot = [IO.Path]::GetFullPath((Join-Path $SINI '..\..\..'))
if ($runtimeRoot -eq $sourceRoot -or $runtimeRoot.StartsWith($sourceRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'FLASK_RUNTIME_DIR must be outside source code'
}
$OUT = Join-Path $runtimeRoot 'build\android'
$artifactDir = Join-Path $runtimeRoot 'data\hp'
$signingDir = Join-Path $runtimeRoot 'secrets\hp\android'
New-Item -ItemType Directory -Force -Path $artifactDir, $signingDir | Out-Null
$APK = Join-Path $artifactDir $(if ($Kandidat) { 'BDM-Saku-kandidat.apk' } else { 'BDM-Saku.apk' })
$KS = Join-Path $signingDir 'bdm-saku.keystore'
$PASS = Join-Path $signingDir 'bdm-saku.keystore.pass'

function Jalankan($exe) {
    & $exe @args
    if ($LASTEXITCODE -ne 0) { throw "$([IO.Path]::GetFileName($exe)) gagal ($LASTEXITCODE)" }
}

$resolvedOut = [IO.Path]::GetFullPath($OUT)
if ($resolvedOut -ne [IO.Path]::GetFullPath((Join-Path $runtimeRoot 'build\android'))) { throw 'Folder build tidak valid' }
if (Test-Path -LiteralPath $resolvedOut) { Remove-Item -LiteralPath $resolvedOut -Recurse -Force }
New-Item -ItemType Directory -Force "$OUT\gen", "$OUT\classes", "$OUT\dex" | Out-Null

# Versi = menit sejak 1 Jan 2026, supaya tiap APK baru (meski di jam yang
# sama) bisa dipasang menimpa yang lama. Ditambah 26.200.000 karena build
# pertama memakai yyMMddHH (26102514) -- versi tidak boleh turun.
$versi = 26200000 + [int]((Get-Date) - (Get-Date '2026-01-01')).TotalMinutes
 $versionFile = Join-Path $artifactDir 'BDM-Saku.versi'
if (Test-Path $versionFile) { $versi = [Math]::Max($versi, [int](Get-Content $versionFile) + 1) }
$nama  = Get-Date -Format 'yyyy.MM.dd'

Write-Host '1/5 sumber daya'
Jalankan "$BT\aapt2.exe" compile --dir "$SINI\res" -o "$OUT\res.zip"
Jalankan "$BT\aapt2.exe" link -o "$OUT\dasar.apk" -I $JAR --manifest "$SINI\AndroidManifest.xml" `
    -A "$SINI\assets" --java "$OUT\gen" --min-sdk-version 24 --target-sdk-version 34 `
    --version-code $versi --version-name $nama "$OUT\res.zip"

Write-Host '2/5 kompilasi Java'
$src = @(Get-ChildItem "$SINI\src", "$OUT\gen" -Recurse -Filter *.java | ForEach-Object FullName)
Jalankan "$JDK\bin\javac.exe" --release 11 -nowarn -encoding UTF-8 -classpath $JAR -d "$OUT\classes" @src

Write-Host '3/5 dex'
$kelas = @(Get-ChildItem "$OUT\classes" -Recurse -Filter *.class | ForEach-Object FullName)
Jalankan "$BT\d8.bat" --release --min-api 24 --lib $JAR --output "$OUT\dex" @kelas
Push-Location "$OUT\dex"
try { Jalankan "$JDK\bin\jar.exe" --update --no-manifest --file "$OUT\dasar.apk" classes.dex } finally { Pop-Location }

Write-Host '4/5 zipalign'
Jalankan "$BT\zipalign.exe" -p -f 4 "$OUT\dasar.apk" "$OUT\rata.apk"

Write-Host '5/5 tanda tangan'
if (-not (Test-Path $KS)) {
    $acak = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    [IO.File]::WriteAllText($PASS, $acak)
    Jalankan "$JDK\bin\keytool.exe" -genkeypair -keystore $KS -alias bdm -keyalg RSA -keysize 2048 `
        -validity 10000 -storepass $acak -keypass $acak -dname 'CN=BDM Saku'
}
Jalankan "$BT\apksigner.bat" sign --ks $KS --ks-key-alias bdm --ks-pass "file:$PASS" `
    --out $APK "$OUT\rata.apk"
Jalankan "$BT\apksigner.bat" verify $APK
# Dibaca kirim_hp.py: HP membandingkan angka ini dengan versinya sendiri untuk
# menawarkan pembaruan saat sinkron.
if (-not $Kandidat) { [IO.File]::WriteAllText($versionFile, "$versi") }

Write-Host ("Selesai: {0} ({1:N1} MB, versi {2})" -f $APK, ((Get-Item $APK).Length / 1MB), $versi)
