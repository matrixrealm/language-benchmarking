FROM maven:3.9.11-eclipse-temurin-25 AS build
WORKDIR /src
COPY pom.xml Main.java ./
RUN mvn -q -DskipTests package
FROM eclipse-temurin:25-jre
WORKDIR /app
COPY --from=build /src/target/classes ./classes
COPY --from=build /src/target/dependency ./lib
CMD ["java", "-Djdk.httpclient.connectionPoolSize=256", "-cp", "classes:lib/*", "Main"]
