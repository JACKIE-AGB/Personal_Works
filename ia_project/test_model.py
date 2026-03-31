#!/usr/bin/env python3
"""
Script para probar la carga del modelo independientemente
"""

import sys
import torch

def test_model_load():
    print("=" * 60)
    print("TEST DE CARGA DEL MODELO")
    print("=" * 60)
    
    print(f"\n1. Python version: {sys.version}")
    print(f"2. PyTorch version: {torch.__version__}")
    print(f"3. CUDA disponible: {torch.cuda.is_available()}")
    
    try:
        import transformers
        print(f"4. Transformers version: {transformers.__version__}")
    except ImportError as e:
        print(f"4. Error importando transformers: {e}")
        return False
    
    try:
        print("\n5. Cargando tokenizer...")
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(
            "microsoft/Phi-3.5-mini-instruct",
            trust_remote_code=True
        )
        print("   ✅ Tokenizer cargado correctamente")
        
        print("\n6. Cargando modelo... (esto tomará unos minutos)")
        from transformers import AutoModelForCausalLM
        
        model = AutoModelForCausalLM.from_pretrained(
            "microsoft/Phi-3.5-mini-instruct",
            torch_dtype=torch.float32,
            device_map="cpu",
            trust_remote_code=True,
            low_cpu_mem_usage=True
        )
        print("   ✅ Modelo cargado correctamente")
        
        print("\n7. Probando generación...")
        from transformers import pipeline
        
        pipe = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            device=-1  # CPU
        )
        
        # Prueba simple
        test_prompt = "Hello, my name is"
        result = pipe(test_prompt, max_new_tokens=20)
        print(f"   ✅ Generación exitosa: {result[0]['generated_text']}")
        
        print("\n" + "=" * 60)
        print("🎉 TODAS LAS PRUEBAS PASARON EXITOSAMENTE")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print(f"Tipo de error: {type(e).__name__}")
        return False

if __name__ == "__main__":
    success = test_model_load()
    sys.exit(0 if success else 1)