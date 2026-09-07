# TrustGuard AI demo app - no custom shrinking rules required (minification disabled).
# Keep kotlinx.serialization generated serializers in case minification is enabled later.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keepclassmembers class kotlinx.serialization.json.** { *** Companion; }
-keepclasseswithmembers class kotlinx.serialization.json.** { kotlinx.serialization.KSerializer serializer(...); }
-keep,includedescriptorclasses class pk.trustguard.**$$serializer { *; }
-keepclassmembers class pk.trustguard.** { *** Companion; }
-keepclasseswithmembers class pk.trustguard.** { kotlinx.serialization.KSerializer serializer(...); }
