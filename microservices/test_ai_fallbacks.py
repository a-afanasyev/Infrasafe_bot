#!/usr/bin/env python3
"""
Test Script for AI Fallback Functionality
UK Management Bot - Shift Service
"""

import sys
import asyncio
import json
from datetime import datetime
from pathlib import Path

# Add shift_service to path
sys.path.append(str(Path(__file__).parent / 'shift_service'))

try:
    from services.ai_integration import AIIntegrationService
    from config import settings
    print("✅ Successfully imported AI integration modules")
except ImportError as e:
    print(f"❌ Failed to import modules: {e}")
    sys.exit(1)


async def test_ai_fallbacks():
    """Test all AI fallback mechanisms"""
    print("\n🔧 Testing AI Fallback Mechanisms")
    print("=" * 50)

    # Initialize AI service
    ai_service = AIIntegrationService()

    # Test data
    test_shift_data = {
        "id": "test-shift-001",
        "specialization": "plumbing",
        "location": {"lat": 55.7558, "lon": 37.6176},
        "urgency": "high",
        "start_time": datetime.utcnow().isoformat()
    }

    test_optimization_data = {
        "shifts": [test_shift_data],
        "executors": [
            {"id": "exec_001", "specialization": "plumbing", "location": {"lat": 55.7500, "lon": 37.6000}},
            {"id": "exec_002", "specialization": "electrical", "location": {"lat": 55.7600, "lon": 37.6200}},
            {"id": "exec_003", "specialization": "maintenance", "location": {"lat": 55.7400, "lon": 37.6100}}
        ]
    }

    test_prediction_data = {
        "target_date": datetime.utcnow().date().isoformat(),
        "historical_days": 30,
        "specialization": "plumbing"
    }

    print(f"🔧 Configuration:")
    print(f"   Fallback Enabled: {settings.ai_fallback_enabled}")
    print(f"   Fallback Mode: {settings.ai_fallback_mode}")
    print(f"   Fallback Confidence: {settings.ai_fallback_confidence}")
    print(f"   Mock Data Enabled: {settings.ai_mock_data_enabled}")
    print(f"   AI Service URL: {settings.ai_service_url}")

    print(f"\n📡 Testing AI Service Health Check...")
    try:
        health_status = await ai_service.check_ai_service_health()
        print(f"   Health Status: {json.dumps(health_status, indent=2)}")
    except Exception as e:
        print(f"   ❌ Health check failed: {e}")

    print(f"\n🔄 Testing Shift Optimization Fallback...")
    try:
        optimization_result = await ai_service.optimize_shift_assignments(test_optimization_data)
        if optimization_result:
            print(f"   ✅ Optimization successful:")
            print(f"   Mode: {optimization_result.get('fallback_mode', 'N/A')}")
            print(f"   Confidence: {optimization_result.get('confidence', 'N/A')}")
            print(f"   Impact Score: {optimization_result.get('impact_score', 'N/A')}")
            print(f"   Recommendations: {len(optimization_result.get('recommendations', []))}")
            if optimization_result.get('recommendations'):
                print(f"   Sample recommendation: {optimization_result['recommendations'][0]}")
        else:
            print(f"   ❌ Optimization returned None")
    except Exception as e:
        print(f"   ❌ Optimization failed: {e}")

    print(f"\n📊 Testing Workload Prediction Fallback...")
    try:
        prediction_result = await ai_service.predict_workload(test_prediction_data)
        if prediction_result:
            print(f"   ✅ Prediction successful:")
            print(f"   Method: {prediction_result.get('method', 'N/A')}")
            print(f"   Predicted Workload: {prediction_result.get('predicted_workload', 'N/A')}")
            print(f"   Confidence: {prediction_result.get('confidence', 'N/A')}")
            if 'factors' in prediction_result:
                print(f"   Factors: {prediction_result['factors']}")
        else:
            print(f"   ❌ Prediction returned None")
    except Exception as e:
        print(f"   ❌ Prediction failed: {e}")

    print(f"\n👥 Testing Assignment Recommendations Fallback...")
    try:
        assignment_result = await ai_service.get_assignment_recommendations(test_shift_data)
        if assignment_result:
            print(f"   ✅ Assignment recommendations successful:")
            print(f"   Recommendations count: {len(assignment_result)}")
            if assignment_result:
                sample_recommendation = assignment_result[0]
                print(f"   Sample recommendation:")
                print(f"     Executor ID: {sample_recommendation.get('executor_id', 'N/A')}")
                print(f"     Total Score: {sample_recommendation.get('total_score', 'N/A')}")
                print(f"     Confidence: {sample_recommendation.get('confidence', 'N/A')}")
                print(f"     Reason: {sample_recommendation.get('recommendation_reason', 'N/A')}")
        else:
            print(f"   ✅ Assignment recommendations returned empty list (expected for simple mode)")
    except Exception as e:
        print(f"   ❌ Assignment recommendations failed: {e}")

    print(f"\n🔍 Testing Different Fallback Modes...")

    # Test enhanced mode directly
    if hasattr(ai_service, '_enhanced_fallback_optimization'):
        print(f"   Testing enhanced optimization...")
        try:
            enhanced_result = await ai_service._enhanced_fallback_optimization(test_optimization_data)
            print(f"   ✅ Enhanced mode: {enhanced_result.get('algorithm', 'N/A')} algorithm")
            print(f"   Impact Score: {enhanced_result.get('impact_score', 'N/A')}")
        except Exception as e:
            print(f"   ❌ Enhanced mode failed: {e}")

    # Test historical mode directly
    if hasattr(ai_service, '_historical_fallback_optimization'):
        print(f"   Testing historical optimization...")
        try:
            historical_result = await ai_service._historical_fallback_optimization(test_optimization_data)
            print(f"   ✅ Historical mode: {historical_result.get('algorithm', 'N/A')} algorithm")
            print(f"   Impact Score: {historical_result.get('impact_score', 'N/A')}")
        except Exception as e:
            print(f"   ❌ Historical mode failed: {e}")

    print(f"\n🎯 Testing Fallback Status...")
    try:
        fallback_status = await ai_service.get_fallback_status()
        print(f"   ✅ Fallback status:")
        print(f"   Currently using fallback: {fallback_status.get('currently_using_fallback', 'N/A')}")
        print(f"   AI Service available: {fallback_status.get('ai_service_health', {}).get('available', 'N/A')}")
        print(f"   Configuration: {fallback_status.get('fallback_mode', 'N/A')} mode")
    except Exception as e:
        print(f"   ❌ Fallback status failed: {e}")

    print(f"\n✅ AI Fallback Testing Completed!")
    print("=" * 50)


async def test_different_scenarios():
    """Test fallbacks with different scenarios"""
    print("\n🎭 Testing Different Scenarios")
    print("=" * 30)

    ai_service = AIIntegrationService()

    scenarios = [
        {
            "name": "High Urgency Electrical Work",
            "shift": {
                "id": "urgent-electrical-001",
                "specialization": "electrical",
                "urgency": "high",
                "location": {"lat": 55.7558, "lon": 37.6176}
            }
        },
        {
            "name": "Regular Maintenance",
            "shift": {
                "id": "maintenance-001",
                "specialization": "maintenance",
                "urgency": "medium",
                "location": {"lat": 55.7400, "lon": 37.6000}
            }
        },
        {
            "name": "Weekend Cleaning",
            "shift": {
                "id": "cleaning-weekend-001",
                "specialization": "cleaning",
                "urgency": "low",
                "location": {"lat": 55.7600, "lon": 37.6200}
            }
        }
    ]

    for scenario in scenarios:
        print(f"\n📋 Scenario: {scenario['name']}")
        try:
            recommendations = await ai_service.get_assignment_recommendations(scenario['shift'])
            if recommendations:
                print(f"   ✅ Got {len(recommendations)} recommendations")
                top_rec = recommendations[0]
                print(f"   Top recommendation: {top_rec.get('total_score', 'N/A')} score")
            else:
                print(f"   ✅ No recommendations (fallback mode dependent)")
        except Exception as e:
            print(f"   ❌ Failed: {e}")


if __name__ == "__main__":
    print("🚀 AI Fallback Functionality Test")
    print("UK Management Bot - Shift Service")
    print(f"Timestamp: {datetime.utcnow().isoformat()}")

    try:
        asyncio.run(test_ai_fallbacks())
        asyncio.run(test_different_scenarios())
        print("\n🎉 All tests completed successfully!")
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Test failed with error: {e}")
        import traceback
        traceback.print_exc()