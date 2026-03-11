from pathlib import Path
from typing import List, Optional


class DockerCommandBuilder:
    """
    A Factory/Builder class for constructing Docker commands.
    """

    class BuildCommandBuilder:
        """
        A builder for constructing 'docker build' commands dynamically.
        """

        def __init__(self, build_context_path: str | Path):
            self._command: List[str] = ["docker", "build"]
            self._options: List[str] = []
            self._tags: List[str] = []
            self._build_args: List[str] = []
            self._labels: List[str] = []
            self._build_context = str(build_context_path)

        def with_dockerfile(self, dockerfile_path: str | Path) -> 'DockerCommandBuilder.BuildCommandBuilder':
            self._command.extend(["-f", str(dockerfile_path)])
            return self

        def with_tag(self, tag: str) -> 'DockerCommandBuilder.BuildCommandBuilder':
            self._tags.extend(["-t", tag])
            return self

        def with_label(self, key: str, value: str) -> 'DockerCommandBuilder.BuildCommandBuilder':
            self._labels.extend(["--label", f"{key}={value}"])
            return self

        def with_build_arg(self, key: str, value: str) -> 'DockerCommandBuilder.BuildCommandBuilder':
            self._build_args.extend(["--build-arg", f"{key}={value}"])
            return self

        def pull_latest_base_image(self, should_pull: bool = True) -> 'DockerCommandBuilder.BuildCommandBuilder':
            if should_pull and "--pull" not in self._options:
                self._options.append("--pull")
            return self

        def without_cache(self, no_cache: bool = True) -> 'DockerCommandBuilder.BuildCommandBuilder':
            if no_cache and "--no-cache" not in self._options:
                self._options.append("--no-cache")
            return self

        def with_progress(self, mode: str = "plain") -> 'DockerCommandBuilder.BuildCommandBuilder':
            self._options.append(f"--progress={mode}")
            return self

        def compile(self) -> List[str]:
            """
            Assembles and returns the final command list for subprocess.
            """
            final_command = self._command.copy()
            final_command.extend(self._options)
            final_command.extend(self._tags)
            final_command.extend(self._labels)
            final_command.extend(self._build_args)

            # Context path MUST be the absolute last argument
            final_command.append(self._build_context)
            return final_command

    class RunCommandBuilder:
        """
        A builder for constructing 'docker run' commands dynamically.
        """

        def __init__(self):
            self._base_command: List[str] = ["docker", "run"]
            self._options: List[str] = []
            self._ports: List[str] = []
            self._env_vars: List[str] = []
            self._volumes: List[str] = []
            self._image: Optional[str] = None
            self._container_args: List[str] = []

        def detached(self, is_detached: bool = True) -> 'DockerCommandBuilder.RunCommandBuilder':
            if is_detached and "-d" not in self._options:
                self._options.append("-d")
            return self

        def with_name(self, name: str) -> 'DockerCommandBuilder.RunCommandBuilder':
            self._options.extend(["--name", name])
            return self

        def with_port_mapping(self, host_port: int | str,
                              container_port: int | str) -> 'DockerCommandBuilder.RunCommandBuilder':
            self._ports.extend(["-p", f"{host_port}:{container_port}"])
            return self

        def with_env(self, key: str, value: str) -> 'DockerCommandBuilder.RunCommandBuilder':
            self._env_vars.extend(["-e", f"{key}={value}"])
            return self

        def with_volume(self, host_path: str | Path,
                        container_path: str | Path) -> 'DockerCommandBuilder.RunCommandBuilder':
            self._volumes.extend(["-v", f"{str(host_path)}:{str(container_path)}"])
            return self

        def with_restart_policy(self, policy: str = "unless-stopped") -> 'DockerCommandBuilder.RunCommandBuilder':
            self._options.extend(["--restart", policy])
            return self

        def with_resource_limits(self, memory: str, cpus: str) -> 'DockerCommandBuilder.RunCommandBuilder':
            if memory:
                self._options.append(f'--memory={memory}')
            if cpus:
                self._options.append(f'--cpus={cpus}')
            return self

        def with_healthcheck(self, cmd: str, interval: str = "30s", timeout: str = "10s",
                             retries: int = 3) -> 'DockerCommandBuilder.RunCommandBuilder':
            self._options.extend([
                f'--health-cmd={cmd}',
                f'--health-interval={interval}',
                f'--health-timeout={timeout}',
                f'--health-retries={str(retries)}'
            ])
            return self

        def with_image(self, image_name: str) -> 'DockerCommandBuilder.RunCommandBuilder':
            self._image = image_name
            return self

        def with_command(self, cmd_string: str) -> 'DockerCommandBuilder.RunCommandBuilder':
            """Optional command to execute inside the container overriding the default entrypoint."""
            self._container_args = cmd_string.split()
            return self

        def with_log_config(self, max_size: str = "10m", max_file: str = "10") -> 'DockerCommandBuilder.RunCommandBuilder':
            """Configures log rotation to prevent disk exhaustion."""
            self._options.extend([
                "--log-driver=json-file",
                f"--log-opt=max-size={max_size}",
                f"--log-opt=max-file={max_file}"
            ])
            return self

        def compile(self) -> List[str]:
            """
            Validates and assembles the run command in the strict order required by Docker.
            """
            if not self._image:
                raise ValueError("Target image is missing. You must call .with_image() before compiling.")

            final_command = self._base_command.copy()
            final_command.extend(self._options)
            final_command.extend(self._ports)
            final_command.extend(self._env_vars)
            final_command.extend(self._volumes)

            # The image MUST come after all flags, but before any container-specific commands
            final_command.append(self._image)
            final_command.extend(self._container_args)

            return final_command

    # Factory Methods
    def build(self, build_context_path: str | Path) -> BuildCommandBuilder:
        return self.BuildCommandBuilder(build_context_path)

    def run(self) -> RunCommandBuilder:
        return self.RunCommandBuilder()