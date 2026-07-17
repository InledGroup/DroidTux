package com.droidtux.bridge;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.drawable.Drawable;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

import java.io.File;
import java.io.FileOutputStream;

/**
 * Servicio de extracción de iconos para DroidTux.
 * Convierte cualquier icono de Android (Adaptive, Legacy, etc.) en un PNG de 512x512.
 */
public class IconService extends Service {
    private static final String TAG = "DroidTuxBridge";

    @Override
    public int onStartCommand(Intent intent, final int flags, final int startId) {
        final String packageName = intent.getStringExtra("package");
        if (packageName != null) {
            new Thread(new Runnable() {
                @Override
                public void run() {
                    if (packageName.equals("all")) {
                        extractAllIcons();
                    } else {
                        extractIcon(packageName);
                    }
                    stopSelf();
                }
            }).start();
        } else {
            stopSelf();
        }
        return START_NOT_STICKY;
    }

    private void extractAllIcons() {
        try {
            PackageManager pm = getPackageManager();
            Intent mainIntent = new Intent(Intent.ACTION_MAIN, null);
            mainIntent.addCategory(Intent.CATEGORY_LAUNCHER);
            java.util.List<android.content.pm.ResolveInfo> apps = pm.queryIntentActivities(mainIntent, 0);
            for (android.content.pm.ResolveInfo app : apps) {
                String pkg = app.activityInfo.packageName;
                extractIcon(pkg);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error query launcher apps: " + e.getMessage());
        }
    }

    private void extractIcon(String pkg) {
        try {
            PackageManager pm = getPackageManager();
            ApplicationInfo appInfo = pm.getApplicationInfo(pkg, 0);
            String label = pm.getApplicationLabel(appInfo).toString();
            Drawable drawable = pm.getApplicationIcon(appInfo);
            
            // Renderizar el drawable a un Bitmap de 512x512
            Bitmap bitmap = Bitmap.createBitmap(512, 512, Bitmap.Config.ARGB_8888);
            Canvas canvas = new Canvas(bitmap);
            drawable.setBounds(0, 0, canvas.getWidth(), canvas.getHeight());
            drawable.draw(canvas);

            // Obtener directorio seguro (Scoped Storage compatible)
            File baseDir = getExternalFilesDir(null);
            if (baseDir == null) {
                baseDir = new File("/sdcard/Download");
            }
            if (!baseDir.exists()) {
                baseDir.mkdirs();
            }

            // Guardar el icono
            File outFile = new File(baseDir, pkg + ".png");
            if (outFile.exists()) outFile.delete();
            FileOutputStream out = new FileOutputStream(outFile);
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, out);
            out.flush();
            out.getFD().sync();
            out.close();

            // Guardar el nombre real de la app
            File labelFile = new File(baseDir, pkg + ".label");
            if (labelFile.exists()) labelFile.delete();
            FileOutputStream labelOut = new FileOutputStream(labelFile);
            labelOut.write(label.getBytes("UTF-8"));
            labelOut.flush();
            labelOut.getFD().sync();
            labelOut.close();
            
            // Notificar al sistema de medios
            android.media.MediaScannerConnection.scanFile(this, 
                new String[]{outFile.getAbsolutePath(), labelFile.getAbsolutePath()}, null, null);
            
            Log.d(TAG, "Extraído con éxito en " + baseDir.getAbsolutePath() + ": " + pkg + " (" + label + ")");
        } catch (Exception e) {
            Log.e(TAG, "Error procesando " + pkg + ": " + e.getMessage());
        }
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }

    @Override
    public void onCreate() {
        super.onCreate();
        // Android 8+ requiere notificación para servicios en primer plano
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel("dt", "DroidTux", NotificationManager.IMPORTANCE_LOW);
            getSystemService(NotificationManager.class).createNotificationChannel(channel);
            startForeground(1, new Notification.Builder(this, "dt")
                .setContentTitle("Extrayendo icono...")
                .setSmallIcon(android.R.drawable.ic_menu_save)
                .build());
        }
    }
}
