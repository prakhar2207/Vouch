package com.srilekh.app;

import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.content.Context;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        
        WebView webView = getBridge().getWebView();
        if (webView != null) {
            WebSettings settings = webView.getSettings();
            settings.setDomStorageEnabled(true);
            settings.setDatabaseEnabled(true);
            
            // Enable offline disk cache
            boolean isOnline = isNetworkAvailable();
            if (isOnline) {
                settings.setCacheMode(WebSettings.LOAD_DEFAULT);
            } else {
                // When offline or in Airplane mode, load cached version from local storage
                settings.setCacheMode(WebSettings.LOAD_CACHE_ELSE_NETWORK);
            }
        }
    }

    private boolean isNetworkAvailable() {
        ConnectivityManager cm = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        if (cm == null) return false;
        android.net.Network activeNetwork = cm.getActiveNetwork();
        if (activeNetwork == null) return false;
        NetworkCapabilities caps = cm.getNetworkCapabilities(activeNetwork);
        return caps != null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
    }
}
