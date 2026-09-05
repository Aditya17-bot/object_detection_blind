package com.blindassist.blindassist

import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.ByteArrayOutputStream

/**
 * Native JPEG encoding for the remote-inference frame path.
 *
 * The app used to POST the camera's RAW YUV420 planes to the laptop: 506 KB
 * for a 720x480 frame. Measured on the user's hotspot that upload alone took
 * 320-510 ms, against ~171 ms for ALL the inference on the other end and a
 * 1.2 s frame timeout. Frames were routinely lost, and a lost frame breaks
 * GuidanceEngine's two-frame persistence streak — which is why obstacles were
 * announced erratically and objects seen only briefly (a door in a doorway)
 * never accumulated enough sightings to be remembered.
 *
 * Android's YuvImage.compressToJpeg is hardware-backed, so this costs a few
 * milliseconds and cuts the payload by roughly 10x. Doing it in Dart instead
 * would mean a per-pixel loop in the UI isolate — the same cost that makes
 * on-device inference unusable on this handset.
 */
class MainActivity : FlutterActivity() {

    companion object {
        private const val CHANNEL = "blindassist/frame"
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "encodeJpeg" -> encodeJpeg(call, result)
                    else -> result.notImplemented()
                }
            }
    }

    private fun encodeJpeg(
        call: io.flutter.plugin.common.MethodCall,
        result: MethodChannel.Result
    ) {
        try {
            val y = call.argument<ByteArray>("y")!!
            val u = call.argument<ByteArray>("u")!!
            val v = call.argument<ByteArray>("v")!!
            val width = call.argument<Int>("width")!!
            val height = call.argument<Int>("height")!!
            val yStride = call.argument<Int>("yStride")!!
            val uvStride = call.argument<Int>("uvStride")!!
            val uvPixelStride = call.argument<Int>("uvPixelStride")!!
            val quality = call.argument<Int>("quality") ?: 80

            val nv21 = toNv21(
                y, u, v, width, height, yStride, uvStride, uvPixelStride
            )
            val out = ByteArrayOutputStream(width * height / 8)
            val ok = YuvImage(nv21, ImageFormat.NV21, width, height, null)
                .compressToJpeg(Rect(0, 0, width, height), quality, out)
            if (!ok) {
                result.error("ENCODE_FAILED", "compressToJpeg returned false", null)
                return
            }
            result.success(out.toByteArray())
        } catch (e: Throwable) {
            // The Dart side falls back to posting raw planes, so a failure here
            // degrades throughput but never stops detection.
            result.error("ENCODE_FAILED", e.message, null)
        }
    }

    /**
     * Repack YUV_420_888 planes as NV21 (full-res Y, then V and U interleaved
     * at half resolution), which is the only 4:2:0 layout YuvImage accepts.
     *
     * Strides are honoured rather than assumed: Android pads rows to hardware
     * alignment, so `yStride` is frequently wider than the image, and chroma
     * arrives either planar (uvPixelStride 1) or already semi-planar
     * (uvPixelStride 2). The semi-planar case is the common one on this
     * handset and gets a row-wise copy instead of a per-pixel loop.
     */
    private fun toNv21(
        y: ByteArray, u: ByteArray, v: ByteArray,
        width: Int, height: Int,
        yStride: Int, uvStride: Int, uvPixelStride: Int
    ): ByteArray {
        val out = ByteArray(width * height * 3 / 2)

        // --- luma: drop the row padding ---
        if (yStride == width) {
            System.arraycopy(y, 0, out, 0, minOf(y.size, width * height))
        } else {
            for (row in 0 until height) {
                val src = row * yStride
                if (src + width > y.size) break
                System.arraycopy(y, src, out, row * width, width)
            }
        }

        // --- chroma: NV21 wants V,U interleaved ---
        var o = width * height
        val chromaH = height / 2
        val chromaW = width / 2
        for (row in 0 until chromaH) {
            val rowStart = row * uvStride
            if (uvPixelStride == 2) {
                // already semi-planar: V and U alternate in each plane, so one
                // strided walk per row beats indexing both buffers per pixel
                var i = rowStart
                var col = 0
                while (col < chromaW) {
                    out[o++] = if (i < v.size) v[i] else 0
                    out[o++] = if (i < u.size) u[i] else 0
                    i += 2
                    col++
                }
            } else {
                var col = 0
                while (col < chromaW) {
                    val i = rowStart + col * uvPixelStride
                    out[o++] = if (i < v.size) v[i] else 0
                    out[o++] = if (i < u.size) u[i] else 0
                    col++
                }
            }
        }
        return out
    }
}
