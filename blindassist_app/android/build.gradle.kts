allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
// Old plugins (vosk_flutter 0.3.48) predate AGP 8's mandatory `namespace`.
// Inject one from the plugin's Gradle group before AGP validates it.
// Reflection because AGP classes aren't on this root script's classpath.
// Must be registered BEFORE the evaluationDependsOn(":app") block below,
// which forces early evaluation.
subprojects {
    afterEvaluate {
        extensions.findByName("android")?.let { ext ->
            val getNamespace = ext.javaClass.getMethod("getNamespace")
            if (getNamespace.invoke(ext) == null) {
                ext.javaClass
                    .getMethod("setNamespace", String::class.java)
                    .invoke(ext, project.group.toString())
            }
            // Old plugins (vosk_flutter) pin compileSdk 33, but their AndroidX
            // deps (fragment 1.7.1, window 1.2.0, ...) require >= 34. Bump any
            // stale module so AAR metadata validation passes.
            val currentSdk = ext.javaClass.getMethod("getCompileSdk").invoke(ext) as? Int
            if (currentSdk != null && currentSdk < 35) {
                ext.javaClass
                    .getMethod("setCompileSdkVersion", String::class.java)
                    .invoke(ext, "android-35")
            }
        }
    }
}

subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
