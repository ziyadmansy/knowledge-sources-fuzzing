plugins {
    kotlin("jvm") version "2.4.20"
    kotlin("plugin.serialization") version "2.4.20"
    application
}
repositories { mavenCentral() }
val kxVersion = (findProperty("kx") as String?) ?: "1.11.0"
dependencies { implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:$kxVersion") }
kotlin { jvmToolchain(21) }
application { mainClass.set("MainKt") }
