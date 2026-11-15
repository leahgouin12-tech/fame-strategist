package com.fame.strategist

import android.Manifest
import android.app.Activity
import android.app.DownloadManager
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.webkit.CookieManager
import android.webkit.PermissionRequest
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

/**
 * The app, which is her laptop's page filling the screen.
 *
 * Everything in this file is plumbing a browser already does, kept because a wrapper that skips
 * any one of it breaks a real flow: DOM storage and cookies so the PIN stays remembered between
 * launches, the file chooser so an upload button opens her photos and camera roll, the permission
 * grant so a capture control works, the download listener so an exported file lands in Downloads,
 * and an error screen that names the address it tried - because "the laptop did not answer" is the
 * one failure this design can produce and the one a blank page would hide.
 */
class BrowserActivity : Activity() {

    private lateinit var web: WebView
    private var baseUrl = ""
    private var picker: ValueCallback<Array<Uri>>? = null
    private var pendingCamera: PermissionRequest? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val url = intent.getStringExtra("url") ?: Prefs.address(this)
        if (url == null) {
            startActivity(Intent(this, MainActivity::class.java))
            finish()
            return
        }

        web = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true          // the shot list keeps state in localStorage
            settings.allowFileAccess = false           // nothing here reads the device by path
            settings.mediaPlaybackRequiresUserGesture = false
            setBackgroundColor(Color.parseColor("#0b0b0c"))
            webViewClient = Client()
            webChromeClient = Chrome()
            setDownloadListener { link, agent, disposition, mime, _ ->
                download(link, agent, disposition, mime)
            }
        }
        CookieManager.getInstance().setAcceptCookie(true)
        baseUrl = url
        loadPage(url)
        setContentView(web)
    }

    private fun loadPage(url: String) {
        web.loadUrl(url)
    }

    override fun onPause() {
        super.onPause()
        CookieManager.getInstance().flush()           // her PIN cookie outlives a killed app
    }

    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else super.onBackPressed()
    }

    // ---- uploads ------------------------------------------------------------

    private inner class Chrome : WebChromeClient() {

        override fun onShowFileChooser(view: WebView, callback: ValueCallback<Array<Uri>>,
                                       params: FileChooserParams): Boolean {
            picker?.onReceiveValue(null)
            picker = callback
            return try {
                startActivityForResult(params.createIntent(), PICK_FILES)
                true
            } catch (e: IllegalStateException) {
                picker = null
                toast("This page asked for a file picker the system does not have.")
                false
            }
        }

        override fun onPermissionRequest(request: PermissionRequest) {
            val wantsCamera = request.resources.any {
                it == PermissionRequest.RESOURCE_VIDEO_CAPTURE
            }
            if (!wantsCamera) {
                request.grant(request.resources)
                return
            }
            if (checkSelfPermission(Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED
            ) {
                request.grant(request.resources)
                return
            }
            pendingCamera = request
            requestPermissions(arrayOf(Manifest.permission.CAMERA), ASK_CAMERA)
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != PICK_FILES) return
        val callback = picker ?: return
        picker = null
        val uris: Array<Uri>? = when {
            resultCode != RESULT_OK -> null
            data?.data != null -> arrayOf(data.data!!)
            else -> data?.clipData?.let { clip ->
                Array(clip.itemCount) { i -> clip.getItemAt(i).uri }
            }
        }
        callback.onReceiveValue(uris)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<String>,
                                            results: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, results)
        val request = pendingCamera ?: return
        pendingCamera = null
        if (results.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            request.grant(request.resources)
        } else {
            request.deny()
            toast("The camera stays off until you allow it in Settings, then Apps.")
        }
    }

    // ---- downloads ----------------------------------------------------------

    /**
     * Saved files go to the public Downloads folder. On Android 9 and below that needs the
     * storage permission the manifest declares with maxSdkVersion; on 10 and up DownloadManager
     * writes there itself, which is why nothing is asked for.
     */
    private fun download(link: String, agent: String, disposition: String, mime: String) {
        val name = fileName(link, disposition)
        try {
            val request = DownloadManager.Request(Uri.parse(link))
                .setMimeType(mime)
                .setUserAgent(agent)
                .setTitle(name)
                .setNotificationVisibility(
                    DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name)
            (getSystemService(DOWNLOAD_SERVICE) as DownloadManager).enqueue(request)
            toast("Saving $name to Downloads.")
        } catch (e: Exception) {
            toast("That file could not be saved: ${e.message}")
        }
    }

    private fun fileName(link: String, disposition: String): String {
        val quoted = Regex("filename\\*?=\"?'?([^\"';]+)\"?'?").find(disposition)?.groupValues?.get(1)
        val candidate = quoted?.trim() ?: Uri.parse(link).lastPathSegment ?: "fame-file"
        val clean = candidate.substringAfterLast('/').replace(Regex("[^A-Za-z0-9._ -]"), "_")
        return if (clean.contains('.')) clean else "$clean.bin"
    }

    // ---- when the laptop does not answer ------------------------------------

    private inner class Client : WebViewClient() {

        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            val host = request.url.host ?: return true
            return host != Uri.parse(baseUrl).host      // anything off this machine leaves the app
        }

        override fun onReceivedError(view: WebView, request: WebResourceRequest,
                                     error: WebResourceError) {
            if (request.isForMainFrame) failed(request.url.toString(), error.description.toString())
        }

        override fun onReceivedHttpError(view: WebView, request: WebResourceRequest,
                                         response: WebResourceResponse) {
            if (request.isForMainFrame && response.statusCode == 401) {
                failed(request.url.toString(), "the page asked for a PIN")
            }
        }
    }

    /** Names the address it tried and offers the two moves that can actually help. */
    private fun failed(url: String, detail: String) {
        val pad = (22 * resources.displayMetrics.density).toInt()
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
            setBackgroundColor(Color.parseColor("#121213"))
        }
        panel.addView(TextView(this).apply {
            text = "The laptop did not answer"
            textSize = 22f
            setTextColor(Color.parseColor("#efe9dc"))
            setPadding(0, 0, 0, (10 * resources.displayMetrics.density).toInt())
        })
        panel.addView(TextView(this).apply {
            text = "Tried $url and got $detail.\n\n" +
                "Usually one of three things: the app is not running on the computer, this phone " +
                "is on a different wifi, or Windows is blocking the port - the /phone screen on " +
                "the laptop has the one-line fix for that."
            textSize = 15f
            setTextColor(Color.parseColor("#efe9dc"))
        })
        panel.addView(Button(this).apply {
            text = "Try again"
            setOnClickListener {
                setContentView(web)
                loadPage(url)
            }
        })
        panel.addView(Button(this).apply {
            text = "Change the address"
            setOnClickListener {
                Prefs.clear(this@BrowserActivity)
                startActivity(Intent(this@BrowserActivity, MainActivity::class.java))
                finish()
            }
        })
        setContentView(panel)
    }

    private fun toast(text: String) =
        Toast.makeText(this, text, Toast.LENGTH_SHORT).show()

    companion object {
        private const val PICK_FILES = 4101
        private const val ASK_CAMERA = 4102
    }
}
