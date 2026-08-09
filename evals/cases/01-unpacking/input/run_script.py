# Load the HERMES record from the YAML file, then run the workflow it describes.

input_yaml_path = "input/config.yaml"

hermes_record = load_hermes_record_from_yaml(input_yaml_path)
workflow = Workflow(hermes_record)
updated_hermes_record = workflow.run()
