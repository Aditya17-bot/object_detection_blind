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
        }
    }
}

subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
