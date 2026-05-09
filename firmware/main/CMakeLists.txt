# Read .env file and create compile definitions
set(ENV_FILE "${CMAKE_SOURCE_DIR}/.env")
if(EXISTS ${ENV_FILE})
    file(STRINGS ${ENV_FILE} ENV_VARS)
    foreach(ENV_VAR ${ENV_VARS})
        if(ENV_VAR MATCHES "^([^=]+)=(.*)$")
            set(ENV_${CMAKE_MATCH_1} "${CMAKE_MATCH_2}")
        endif()
    endforeach()
endif()

idf_component_register(SRCS "main.c" "sensor.c" "wifi.c" "beacon.c" "auth.c" "kms.c" "time_sync.c"
                       INCLUDE_DIRS ".")

# Pass .env values as compile definitions
if(DEFINED ENV_WIFI_SSID)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE
        WIFI_SSID="${ENV_WIFI_SSID}"
        WIFI_PASS="${ENV_WIFI_PASS}"
    )
else()
    message(WARNING ".env file missing WIFI_SSID/WIFI_PASS – WiFi will not work")
    target_compile_definitions(${COMPONENT_LIB} PRIVATE
        WIFI_SSID="CHANGEME"
        WIFI_PASS="CHANGEME"
    )
endif()

# Orbitport credentials
if(DEFINED ENV_USER_ID)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE
        USER_ID="${ENV_USER_ID}"
        SECRET="${ENV_SECRET}"
    )
else()
    message(WARNING ".env file missing USER_ID/SECRET – auth will not work")
    target_compile_definitions(${COMPONENT_LIB} PRIVATE
        USER_ID="CHANGEME"
        SECRET="CHANGEME"
    )
endif()
