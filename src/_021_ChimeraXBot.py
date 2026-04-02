import os
import sys
from chimerax.core.commands import run

# Runs inside ChimeraX (nogui). No prompts.
if len(sys.argv) < 2:
    print("Usage: chimerax --nogui ChimeraX_execution_script.py <path_to_.cxc> [sim_id]")
    sys.exit(1)

AlignInput = sys.argv[1]
sim_filter = sys.argv[2] if len(sys.argv) >= 3 else None

def process_job_folders(session):
    # Project root = one level up from this script
    script_dir = os.path.dirname(os.path.realpath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, os.pardir))

    af3_output_dir = os.path.join(project_root, "AF3_output")
    if not os.path.isdir(af3_output_dir):
        print(f"ERROR: Cannot find AF3_output/ under {project_root}")
        return

    if not os.path.isfile(AlignInput):
        print(f"ERROR: ChimeraX script not found at: {AlignInput}")
        return

    # Gather run folders (e.g., "0009", "0012"), optionally filter by sim_id
    run_folders = [
        d for d in os.listdir(af3_output_dir)
        if os.path.isdir(os.path.join(af3_output_dir, d)) and not d.startswith("__")
    ]
    if sim_filter:
        run_folders = [d for d in run_folders if d == sim_filter]

    if not run_folders:
        print(f"ERROR: No run subfolders found under {af3_output_dir}"
              + (f" matching sim_id '{sim_filter}'" if sim_filter else ""))
        return

    # Base ChimeraX output dir: ChimeraX/<SimID>/<cx_base>/
    cx_scripts_dir = os.path.join(project_root, "ChimeraX")
    cx_base = os.path.splitext(os.path.basename(AlignInput))[0]

    for run_folder in run_folders:
        run_path = os.path.join(af3_output_dir, run_folder)
        print("\nProcessing run folder:", run_path)

        chimx_out_dir = os.path.join(cx_scripts_dir, run_folder, cx_base)
        pre_out_dir   = os.path.join(chimx_out_dir, "PreModels")
        os.makedirs(chimx_out_dir, exist_ok=True)
        os.makedirs(pre_out_dir,   exist_ok=True)

        # Job subfolders (e.g., "0012_01_…")
        job_folders = [
            f for f in os.listdir(run_path)
            if os.path.isdir(os.path.join(run_path, f)) and not f.startswith("__")
        ]
        print("  Found job folders:", job_folders)

        for job in job_folders:
            job_path = os.path.join(run_path, job)
            print("    Processing job folder:", job_path)

            # Accept common AF3 outputs: any .cif or .pdb
            struct_files = sorted(
                f for f in os.listdir(job_path)
                if f.lower().endswith((".cif", ".pdb"))
            )
            if not struct_files:
                print(f"    Warning: No CIF/PDB model files found in {job_path} -> skipping.")
                continue

            # Open structures (QUOTE PATHS!)
            for sf in struct_files:
                sf_path = os.path.join(job_path, sf)
                print("      Opening structure:", sf_path)
                run(session, f'open "{sf_path}"')

            # Sanity check: ensure we actually opened models
            n_models = len(session.models)
            print(f"      Models open after load: {n_models}")
            if n_models == 0:
                print("      ERROR: 0 models open after 'open' commands; skipping this job.")
                run(session, "close session")
                continue

            # Save a PRE-script snapshot for debugging into PreModels/
            pre_file = os.path.join(pre_out_dir, f"{job}__pre.cxs")
            print("      Saving PRE-script session to:", pre_file)
            run(session, f'save "{pre_file}"')

            # Run the .cxc (QUOTE PATH!). Errors are logged but not fatal.
            print("      Running external alignment script:", AlignInput)
            try:
                run(session, f'runscript "{AlignInput}"')
            except Exception as e:
                print(f"      WARNING: cxc failed for job '{job}': {e}")

            # Save final session into main output dir
            output_file = os.path.join(chimx_out_dir, f"{job}.cxs")
            print("      Saving session to:", output_file)
            run(session, f'save "{output_file}"')

            # Clean up for next job
            print("      Clearing session for next job…")
            run(session, "close session")

    # Exit ChimeraX after all runs
    run(session, "exit")

process_job_folders(session)
