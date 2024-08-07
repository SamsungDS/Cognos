
file(COPY ${PARENT_DIR}/systemd_files/svk-controller.service DESTINATION ${CMAKE_INSTALL_PREFIX}/etc/systemd/system)
file(COPY ${PARENT_DIR}/systemd_files/svk-node.service DESTINATION ${CMAKE_INSTALL_PREFIX}/etc/systemd/system)
file(COPY ${PARENT_DIR}/systemd_files/svk-restserver.service DESTINATION ${CMAKE_INSTALL_PREFIX}/etc/systemd/system)
