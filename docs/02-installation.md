# 2. Installation

Anaconda Prompt is needed prior to using *batplot*. Anaconda is a distribution platform for Python that manages different Python versions and packages. The key tool is a command called conda, which is a package and environment manager.

*batplot* relies on packages such as *matplotlib* and *numpy* for its functionality. These packages come in different versions that you may already have that are not compatible with *batplot*. By using conda, you can create an isolated environment so *batplot* installs the exact versions it needs.

__Step 1: Download Anaconda Prompt__

Download and install Anaconda from the official Anaconda website: https://www.anaconda.com/download

Once installation is complete, search for a program called Anaconda Prompt. You will see a terminal window with (base) shown on the far left of the prompt line, indicating the default conda environment.

__Step 2: Create a dedicated batplot environment__

In the Anaconda Prompt, type the following command:

```text
conda create -n batplot python=3.13
```

conda will resolve the environment and ask you to confirm. Type Y and press Enter to proceed. This creates a new isolated Python 3.13 environment named batplot.

!!! note

    On some systems the version number must be quoted:

    ```text
    conda create -n batplot python="3.13"
    ```

__Step 3: Activate the batplot environment__

Activate the newly created environment:

```text
conda activate batplot
```

The label on the far left of the prompt will change from (base) to (batplot), confirming that the environment is now active.

__Step 4: Install batplot__

Install batplot from PyPI:

```text
pip install batplot
```

(Alternatively, in any Python ≥ 3.9 environment: `python -m pip install batplot`.)

pip will automatically download batplot and all required dependencies (*matplotlib*, *numpy*, etc.) into the batplot environment.

__Step 5: Verify the installation__

Confirm that batplot installed correctly by running:

```text
batplot --help
```

After a few seconds a help message will appear. At the top of the message you should see the current version number (e.g., v1.8.29). If you see this, the installation was successful.

__*batplot* only works inside its conda environment. Each time before using, open Anaconda Prompt and activate the environment first:__

```text
conda activate batplot
```

!!! note

    batplot is actively developed. New features are added regularly.

