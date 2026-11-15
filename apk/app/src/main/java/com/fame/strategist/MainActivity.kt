package com.fame.strategist

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView

/**
 * The one screen that is not her app. It exists because nothing can guess the address of the
 * laptop on her wifi, and because typing it once should be the entire setup: it is remembered,
 * and every later launch goes straight to BrowserActivity.
 */
class MainActivity : Activity() {

    private lateinit var field: EditText
    private lateinit var problem: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Prefs.address(this)?.let { open(it) } ?: form()
    }

    private fun form() {
        val pad = dp(22)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
            gravity = Gravity.CenterVertical
        }

        root.addView(TextView(this).apply {
            text = "Where is your laptop?"
            textSize = 26f
            setPadding(0, 0, 0, dp(10))
        })

        root.addView(TextView(this).apply {
            text = "Fame Strategist runs on your computer, not on this phone. Type the address " +
                "the app shows you there at /phone - it looks like 192.168.1.20:8756. " +
                "Both have to be on the same wifi."
            textSize = 15f
            setPadding(0, 0, 0, dp(18))
        })

        field = EditText(this).apply {
            hint = "192.168.1.20:8756"
            inputType = InputType.TYPE_CLASS_TEXT or
                InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            textSize = 17f
        }
        root.addView(field)

        problem = TextView(this).apply {
            textSize = 14f
            setPadding(dp(2), dp(10), 0, 0)
            visibility = ViewGroup.INVISIBLE
        }
        root.addView(problem)

        root.addView(Button(this).apply {
            text = "Open"
            textSize = 17f
            setOnClickListener { submit() }
        })

        setContentView(root)
    }

    private fun submit() {
        val raw = field.text.toString()
        when (val result = Addresses.parse(raw)) {
            is Addresses.Outcome.Good -> {
                Prefs.save(this, result.url)
                open(result.url)
            }
            is Addresses.Outcome.Bad -> {
                problem.text = result.reason
                problem.visibility = ViewGroup.VISIBLE
            }
        }
    }

    private fun open(url: String) {
        startActivity(Intent(this, BrowserActivity::class.java).putExtra("url", url))
        finish()
    }

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).toInt()
}

/** One place the saved address lives, so the setup screen and the error screen agree. */
object Prefs {
    private const val NAME = "fame"
    private const val KEY = "address"

    fun address(activity: Activity): String? =
        activity.getSharedPreferences(NAME, Activity.MODE_PRIVATE).getString(KEY, null)

    fun save(activity: Activity, url: String) {
        activity.getSharedPreferences(NAME, Activity.MODE_PRIVATE)
            .edit().putString(KEY, url).apply()
    }

    fun clear(activity: Activity) {
        activity.getSharedPreferences(NAME, Activity.MODE_PRIVATE)
            .edit().remove(KEY).apply()
    }
}

/**
 * Text in, usable URL out. Two rules, both of them about not failing quietly later: the host is
 * checked while she is still typing rather than after a spinner, and a missing port becomes the
 * port the server actually listens on instead of 80.
 */
object Addresses {
    const val DEFAULT_PORT = 8756

    sealed class Outcome {
        data class Good(val url: String) : Outcome()
        data class Bad(val reason: String) : Outcome()
    }

    fun parse(raw: String): Outcome {
        val trimmed = raw.trim().removeSuffix("/")
        if (trimmed.isEmpty()) return Outcome.Bad("Type the address the app shows you.")
        if (trimmed.any { it.isWhitespace() }) {
            return Outcome.Bad("An address has no spaces in it.")
        }

        val uri = runCatching { Uri.parse(if (trimmed.contains("://")) trimmed else "http://$trimmed") }
            .getOrNull()
        val host = uri?.host
        if (host.isNullOrBlank()) return Outcome.Bad("That is not an address yet.")

        if (!host.matches(NAME_OR_IP) && !isPrivate(host)) {
            return Outcome.Bad("Only an address on your own wifi works - something like " +
                "192.168.1.20:$DEFAULT_PORT.")
        }

        val port = if (uri.port > 0) uri.port else DEFAULT_PORT
        val scheme = uri.scheme ?: "http"
        return Outcome.Good("$scheme://$host:$port")
    }

    /** A dotted name is allowed unresolved: a laptop's mDNS name is a normal thing to type. */
    private val NAME_OR_IP = Regex("^[A-Za-z0-9_.-]+\\.[A-Za-z0-9-]+$")

    fun isPrivate(host: String): Boolean {
        val octets = host.split(".").map { it.toIntOrNull() ?: return false }
        if (octets.size != 4 || octets.any { it !in 0..255 }) return false
        return when (octets[0]) {
            10 -> true
            127 -> true
            172 -> octets[1] in 16..31
            192 -> octets[1] == 168
            else -> false
        }
    }
}
