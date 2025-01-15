import os
import sys
import tempfile
import subprocess

################################################################################
# RUN STARTUP WITH macOS TERMINAL LOGGING                                      #
################################################################################

import sgtk
from sgtk.platform import SoftwareLauncher, SoftwareVersion, LaunchInformation

class BlenderLauncher(SoftwareLauncher):
    """
    Custom Blender launcher that spawns a new macOS Terminal window
    so you can see stdout/stderr output.
    """

    COMPONENT_REGEX_LOOKUP = {"version": r"\d.\d+(.\d*)*"}
    EXECUTABLE_TEMPLATES = {
        "darwin": [
            "$BLENDER_BIN_DIR/Blender {version}",
            "/Applications/Blender{version}.app/Contents/MacOS/Blender",
        ],
        # Windows and Linux omitted for brevity...
    }

    @property
    def minimum_supported_version(self):
        return "2.8"

    def prepare_launch(self, exec_path, args, file_to_open=None):
        """
        Prepares the environment and (instead of returning a normal LaunchInformation),
        spawns Blender in a new Terminal window via AppleScript, capturing stdout/stderr there.
        """

        # ---------------------------------------------------------------------
        # 1) Let the normal logic build the environment variables we need
        # ---------------------------------------------------------------------
        required_env = {}

        # Example: standard environment-building from your existing code
        scripts_path = os.path.join(self.disk_location, "resources", "scripts")
        startup_path = os.path.join(scripts_path, "startup", "Shotgun_menu.py")
        args += "-P " + startup_path

        required_env["BLENDER_USER_SCRIPTS"] = scripts_path

        if not os.environ.get("PYSIDE2_PYTHONPATH"):
            pyside2_python_path = os.path.join(self.disk_location, "python", "ext")
            required_env["PYSIDE2_PYTHONPATH"] = pyside2_python_path

        required_env["SGTK_MODULE_PATH"] = sgtk.get_sgtk_module_path().replace("\\", "/")
        engine_startup_path = os.path.join(self.disk_location, "startup", "bootstrap.py")
        required_env["SGTK_BLENDER_ENGINE_STARTUP"] = engine_startup_path
        required_env["SGTK_BLENDER_ENGINE_PYTHON"] = sys.executable.replace("\\", "/")
        required_env["SGTK_ENGINE"] = self.engine_name
        required_env["SGTK_CONTEXT"] = sgtk.context.serialize(self.context)

        if file_to_open:
            required_env["SGTK_FILE_TO_OPEN"] = file_to_open

        # ---------------------------------------------------------------------
        # 2) Build a small shell script that sets env vars, then calls Blender
        # ---------------------------------------------------------------------
        shell_script_lines = [
            "#!/bin/bash\n",
            "# Auto-generated script to launch Blender in a Terminal\n",
        ]
        # Export each environment variable
        for key, val in required_env.items():
            # Escape any quotes
            val_escaped = val.replace('"', '\\"')
            shell_script_lines.append(f'export {key}="{val_escaped}"\n')
        # Finally call Blender
        # `args` might contain multiple tokens; ensure we keep them intact
        shell_script_lines.append(f'"{exec_path}" {args}\n')
        # Keep terminal open so user can see output
        shell_script_lines.append('read -p "Press [Enter] to close this window..."\n')

        # Write this script to a temp file
        tmp_file = tempfile.NamedTemporaryFile(delete=False, mode="w", prefix="blender_launch_", suffix=".sh")
        script_path = tmp_file.name
        tmp_file.writelines(shell_script_lines)
        tmp_file.close()

        # Make it executable
        os.chmod(script_path, 0o755)

        # ---------------------------------------------------------------------
        # 3) Use AppleScript to open a new Terminal window that runs our script
        # ---------------------------------------------------------------------
        # Because we want a brand new Terminal window, we can do:
        apple_script = f'''
            tell application "Terminal"
                activate
                do script "{script_path}"
            end tell
        '''
        # Launch the AppleScript (async).
        subprocess.Popen(["osascript", "-e", apple_script])

        # ---------------------------------------------------------------------
        # 4) Return a "dummy" LaunchInformation (if the calling code expects it)
        # ---------------------------------------------------------------------
        return LaunchInformation(
            None, None, None
        )

    def _icon_from_engine(self):
        engine_icon = os.path.join(self.disk_location, "icon_256.png")
        return engine_icon

    def scan_software(self):
        """
        Scan the filesystem for blender executables.

        :return: A list of :class:`SoftwareVersion` objects.
        """
        self.logger.debug("Scanning for Blender executables...")

        supported_sw_versions = []
        for sw_version in self._find_software():
            (supported, reason) = self._is_supported(sw_version)
            if supported:
                supported_sw_versions.append(sw_version)
            else:
                self.logger.debug(
                    "SoftwareVersion %s is not supported: %s" % (sw_version, reason)
                )

        return supported_sw_versions

    def _find_software(self):
        executable_templates = self.EXECUTABLE_TEMPLATES.get(sys.platform, [])
        sw_versions = []
        extra_args = os.environ.get("SGTK_BLENDER_CMD_EXTRA_ARGS")

        for executable_template in executable_templates:
            executable_template = os.path.expanduser(executable_template)
            executable_template = os.path.expandvars(executable_template)
            self.logger.debug("Processing template %s", executable_template)

            executable_matches = self._glob_and_match(
                executable_template, self.COMPONENT_REGEX_LOOKUP
            )

            for (executable_path, key_dict) in executable_matches:
                executable_version = key_dict.get("version", " ")
                args = []
                if extra_args:
                    args.append(extra_args)

                sw_versions.append(
                    SoftwareVersion(
                        executable_version,
                        "Blender",
                        executable_path,
                        icon=self._icon_from_engine(),
                        args=args,
                    )
                )

        return sw_versions
