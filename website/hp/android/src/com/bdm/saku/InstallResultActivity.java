package com.bdm.saku;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.os.Bundle;
import android.widget.Toast;

/** Receives installation results through a session-specific PendingIntent. */
public final class InstallResultActivity extends Activity {
    @Override
    @SuppressWarnings("deprecation")
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        try {
            Intent result = getIntent();
            int status = result.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
            if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
                Intent confirmation = result.getParcelableExtra(Intent.EXTRA_INTENT);
                if (confirmation != null) startActivity(confirmation);
            } else if (status != PackageInstaller.STATUS_SUCCESS) {
                String reason = result.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
                Toast.makeText(this, "Pembaruan gagal" + (reason == null ? "" : ": " + reason),
                        Toast.LENGTH_LONG).show();
            }
        } finally {
            finish();
        }
    }
}
