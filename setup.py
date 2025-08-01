from setuptools import setup, find_packages

def parse_requirements(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.startswith("#")
        ]


setup(
    name="cont_sys_sim",
    version="1.0.0",
    author="Milan Balazs",
    author_email="milanbalazs01@gmail.com",
    description=(
        "A SimPy-based Containerized environment (Eg.: Docker Swarm) "
        "simulation with Nodes and Containers"
    ),
    long_description=open("README.md", "r", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/milanbalazs/ContSysSim",
    packages=find_packages(where="src"),  # Discover packages inside `src`
    package_dir={"": "src"},  # Define src as the package directory
    install_requires=parse_requirements("requirements.txt"),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.11",
    include_package_data=True,
    # entry_points={
    #     "console_scripts": [
    #         "run_simulation=examples.multi_node:MultiNodeSimulation",
    #     ],
    # },
    keywords="Container Containerized System Docker Swarm SimPy Simulation",
)
