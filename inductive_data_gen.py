import argparse
import random
import networkx as nx

def build_graph_from_rdf(rdf_triples):
    G = nx.Graph()
    for h, r, t in rdf_triples:
        G.add_edge(h, t, relation=r)
    return G

def find_gccs(G):
    gccs = list(nx.connected_components(G))
    return gccs

def get_two_hop_neighbors(G, nodes, limit=50):
    extended_nodes = set()
    for node in nodes:
        neighbors = set(nx.single_source_shortest_path_length(G, node, cutoff=2).keys())
        if len(neighbors) > limit:
            neighbors = set(random.sample(list(neighbors), limit))
        extended_nodes.update(neighbors)
    return list(extended_nodes)

# Function to read RDF triples from a file
def read_rdf_triples(file_path):
    with open(file_path, 'r') as file:
        triples = [line.strip().split() for line in file.readlines()]
    return triples

# Function to write RDF triples to a file
def write_rdf_triples(file_path, triples):
    with open(file_path, 'w') as file:
        for triple in triples:
            file.write(' '.join(triple) + '\n')

### Algorithm 2: Generating Datasets for Inductive Knowledge Graph Completion
# **Input:**  
# \(\tilde{G} = (V, R, E)\), \(n_{tr}\), \(n_{inf}\), \(p_{rel}\), \(p_{tri}\)
#
# **Output:**  
# \(G_{tr} = (V_{tr}, R_{tr}, E_{tr})\) and \(G_{inf} = (V_{inf}, R_{inf}, E_{inf})\)
#
# 1. \(G \leftarrow\) Giant connected component of \(\tilde{G}\).
# 2. Randomly split \(R\) into \(R_{tr}\) and \(R_{inf}\) such that \(|R_{tr}| : |R_{inf}| = (1 - p_{rel}) : p_{rel}\).
# 3. Uniformly sample \(n_{tr}\) entities from \(V\) and form \(V_{tr}\) by taking the sampled entities and their two-hop neighbors. We select at most 50 neighbors per entity for each hop to prevent exponential growth.
# 4. \(E_{tr} \leftarrow \{(v_i, r, v_j)\} \subseteq E\) where \(v_i, v_j \in V_{tr}\), \(r \in R_{tr}\), \((v_i, r, v_j) \in E\}\).
# 5. \(E_{tr}\) is the giant connected component of \(E_{tr}\).
# 6. \(V_{tr}\) ← Entities involved in \(E_{tr}\).
# 7. \(R_{tr}\) ← Relations involved in \(E_{tr}\).
# 8. Let \(G'\) be the subgraph of \(G\) where the entities in \(V_{tr}\) are removed.
# 9. In \(G'\), uniformly sample \(n_{inf}\) entities and form \(V_{inf}\) by taking the sampled entities and their two-hop neighbors. We select at most 50 neighbors per entity for each hop to prevent exponential growth.
# 10. \(E_{inf} \leftarrow \{(v_i, r, v_j)\} \subseteq E\) where \(v_i \in V_{inf}\), \(v_j \in V_{inf}\), \(r \in R_{inf}\), \((v_i, r, v_j) \in E\}\) and \(|J| = (1 - p_{tri}) : p_{tri}\) where \(J\) is the set of all possible triples.
# 11. \(E_{inf}\) ← Triplets in the giant connected component of \(E_{inf}\).
# 12. \(V_{inf}\) ← Entities involved in \(E_{inf}\).
# 13. \(R_{inf}\) ← Relations involved in \(E_{inf}\).
#
# As additional context, this algorithm is used to generate datasets for evaluating models on inductive knowledge graph completion tasks, where the model needs to predict new information about entities not seen during training.
# Function to generate inductive datasets
def generate_inductive_datasets(input_file, output_prefix, n_tr, n_inf, p_rel, p_tri):
    # Read the RDF triples from the input file
    rdf_triples = read_rdf_triples(input_file)
    G = build_graph_from_rdf(rdf_triples)

    # Identify all Giant Connected Components (GCCs)
    gccs = find_gccs(G)

    # Initialize containers for the training and inductive datasets
    rdf_triples_G_tr = []
    rdf_triples_G_inf = []

    # Process each GCC
    for gcc in gccs:
        sub_G = G.subgraph(gcc).copy()

        # Step 2: Randomly split R into R_tr and R_inf
        R = list(set(sub_G.edges(data='relation')))
        random.shuffle(R)
        split_index = int(p_rel * len(R))
        R_tr = R[:split_index]
        R_inf = R[split_index:]

        # Step 3: Sample n_tr entities from V and form V_tr with two-hop neighbors
        V = list(sub_G.nodes())
        random.shuffle(V)
        V_tr_sampled = V[:n_tr]
        V_tr = get_two_hop_neighbors(sub_G, V_tr_sampled, limit=50)

        # Step 4: Construct E_tr
        E_tr = [(h, r, t) for h, r, t in sub_G.edges(data='relation') if h in V_tr and (h, t, r) in R_tr]

        # Convert E_tr to a NetworkX graph to process further
        G_tr = nx.Graph()
        for h, r, t in E_tr:
            G_tr.add_edge(h, t, relation=r)

        # Check if G_tr is empty
        if G_tr.number_of_nodes() == 0:
            print("Warning: G_tr is empty. Skipping this GCC.")
            continue  # Skip the rest of the loop and move to the next GCC

        # Step 5: Identify the GCC of E_tr
        largest_cc = max(nx.connected_components(G_tr), key=len)
        G_tr_gcc = G_tr.subgraph(largest_cc).copy()

        # Step 6: Update V_tr based on entities in the GCC of E_tr
        V_tr = list(G_tr_gcc.nodes())

        # Step 7: Update R_tr based on relations in the GCC of E_tr
        R_tr = list(set(nx.get_edge_attributes(G_tr_gcc, 'relation').values()))

        # Step 8: Construct G' and repeat sampling for V_inf
        G_prime_nodes = set(sub_G.nodes()) - set(V_tr)
        G_prime = sub_G.subgraph(G_prime_nodes).copy()

        # Step 9: In G', uniformly sample n_inf entities and form V_inf by taking the sampled entities and their two-hop neighbors
        V_inf_sampled = random.sample(G_prime_nodes, n_inf)
        V_inf = get_two_hop_neighbors(G_prime, V_inf_sampled, limit=50)

        # Step 10: Construct E_inf
        E_inf = [(h, r, t) for h, r, t in G_prime.edges(data='relation') if h in V_inf and (h, t, r) in R_inf]

        # Convert E_inf to a NetworkX graph to process further
        G_inf = nx.Graph()
        for h, r, t in E_inf:
            G_inf.add_edge(h, t, relation=r)

        # Step 11: Identify the GCC of E_inf
        largest_cc_inf = max(nx.connected_components(G_inf), key=len)
        G_inf_gcc = G_inf.subgraph(largest_cc_inf).copy()

        # Step 12: Update V_inf based on entities in the GCC of E_inf
        V_inf = list(G_inf_gcc.nodes())

        # Step 13: Update R_inf based on relations in the GCC of E_inf
        R_inf = list(set(nx.get_edge_attributes(G_inf_gcc, 'relation').values()))

        # Format and append the triples for G_tr and G_inf using the updated V_tr, R_tr, V_inf, and R_inf
        rdf_triples_G_tr.extend(['<{}> <{}> <{}>'.format(h, r, t) for h, r, t in G_tr.edges(data='relation')])
        rdf_triples_G_inf.extend(['<{}> <{}> <{}>'.format(h, r, t) for h, r, t in G_inf_gcc.edges(data='relation')])

    # Output the RDF triples in the requested format
    write_rdf_triples(f'{output_prefix}_tr.txt', rdf_triples_G_tr)
    write_rdf_triples(f'{output_prefix}_inf.txt', rdf_triples_G_inf)

    return f'{output_prefix}_tr.txt', f'{output_prefix}_inf.txt'

# Argument parser for command line interface
def parse_arguments():
    parser = argparse.ArgumentParser(description='Generate Datasets for Inductive Knowledge Graph Completion')
    parser.add_argument('-i', '--input', required=True, help='Input file containing RDF triples')
    parser.add_argument('-o', '--output', required=True, help='Output prefix for the generated datasets')
    return parser.parse_args()

# If this script is run as the main program
if __name__ == '__main__':
    # Parse the command line arguments
    args = parse_arguments()

    # Parameters (example values, these could be arguments as well)
    n_tr = 5000  # number of entities to sample for training set
    n_inf = 10000 # number of entities to sample for inductive set
    p_rel = 0.7  # probability of selecting a relation for the training set
    p_tri = 0.7  # probability of selecting a triplet for the training set

    # Generate the inductive datasets
    output_tr, output_inf = generate_inductive_datasets(args.input, args.output, n_tr, n_inf, p_rel, p_tri)

    # Print out the names of the generated files
    print(f'Training dataset written to {output_tr}')
    print(f'Inductive dataset written to {output_inf}')