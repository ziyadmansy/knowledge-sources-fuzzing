// Kotlin counterpart of the previous study's Dart harness: one long-lived process, NDJSON over
// stdin/stdout, four deserialization paths run on every input (docs/design.md §5.2, §10).
// Every library is used at its documented defaults; versions are pinned for the paper.
plugins {
    kotlin("jvm") version "2.4.20"
    kotlin("plugin.serialization") version "2.4.20"
    id("com.google.devtools.ksp") version "2.3.12"
    application
}

repositories { mavenCentral() }

dependencies {
    implementation("com.google.code.gson:gson:2.14.0")
    implementation("com.squareup.moshi:moshi:1.15.2")
    ksp("com.squareup.moshi:moshi-kotlin-codegen:1.15.2")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.11.0")
    implementation("com.fasterxml.jackson.module:jackson-module-kotlin:2.22.3")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.22.3")
}

kotlin { jvmToolchain(21) }

application { mainClass.set("harness.MainKt") }
